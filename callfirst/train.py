"""Train, select on validation, calibrate, then score the held-out test split once.

    python -m callfirst.train            # full run (about 2-4 minutes on a laptop CPU)
    python -m callfirst.train --quick    # 200 bootstrap resamples, for a fast check

Writes artifacts/bundle.joblib and artifacts/worklist.json (demo), and
reports/metrics.json and reports/EVALUATION.md (results).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.isotonic import IsotonicRegression

from . import config, data, lace, metrics, model
from .report import write_markdown


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def age_band(years: np.ndarray) -> np.ndarray:
    return np.where(years < 60, "under 60", np.where(years < 80, "60-79", "80+"))


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="fewer bootstrap resamples")
    args = ap.parse_args(argv)
    n_boot = 200 if args.quick else config.BOOTSTRAP_RESAMPLES
    t0 = time.time()

    raw = data.load_raw()
    df = data.clean(raw)
    X = data.build_features(df)
    y = df["y"].to_numpy()
    lace_df = lace.lace_components(df)
    sp = data.split_by_patient(df)
    groups = df["patient_nbr"].to_numpy()
    assert not set(groups[sp.train]) & set(groups[sp.test])
    assert not set(groups[sp.valid]) & set(groups[sp.test])
    assert not set(groups[sp.train]) & set(groups[sp.valid])
    print(f"encounters {len(df)}  train {len(sp.train)}  valid {len(sp.valid)}  test {len(sp.test)}")

    Xtr, ytr = X.iloc[sp.train], y[sp.train]
    Xva, yva = X.iloc[sp.valid], y[sp.valid]
    Xte, yte = X.iloc[sp.test], y[sp.test]

    # ---- model selection on validation only ----
    selection = {"logistic": [], "boosting": []}
    best = {}
    for C in config.LOGREG_C_GRID:
        p = model.logistic(C, config.SEED).fit(Xtr, ytr)
        a = metrics.auroc(yva, p.predict_proba(Xva)[:, 1])
        selection["logistic"].append({"C": C, "valid_auroc": a})
        if a > best.get("logistic", (None, -1, None))[1]:
            best["logistic"] = ({"C": C}, a, p)
        print(f"logistic C={C}: valid AUROC {a:.4f}")
    for params in config.HGB_GRID:
        p = model.boosting(params, config.SEED).fit(Xtr, ytr)
        a = metrics.auroc(yva, p.predict_proba(Xva)[:, 1])
        selection["boosting"].append({**params, "valid_auroc": a})
        if a > best.get("boosting", (None, -1, None))[1]:
            best["boosting"] = (params, a, p)
        print(f"boosting {params}: valid AUROC {a:.4f}")

    gain = best["boosting"][1] - best["logistic"][1]
    chosen = "boosting" if gain >= config.MIN_AUROC_GAIN_FOR_COMPLEX_MODEL else "logistic"
    params, _, pipe = best[chosen]
    print(f"chosen: {chosen} (boosting - logistic valid AUROC = {gain:+.4f})")

    valid_scores = pipe.predict_proba(Xva)[:, 1]
    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(valid_scores, yva)

    trva = np.r_[sp.train, sp.valid]
    lace_table = pd.Series(y[trva]).groupby(lace_df["lace"].to_numpy()[trva]).agg(["mean", "size"])
    lace_risk = {int(k): float(v) for k, v in lace_table["mean"].items()}

    options = {c: sorted(X[c].unique().tolist()) for c in data.CATEGORICAL}
    bundle = model.Bundle(
        name=chosen, params=params, pipeline=pipe, calibrator=calibrator,
        reference=model.reference_values(Xtr), valid_scores=valid_scores,
        lace_risk=lace_risk, options=options,
    )
    config.ARTIFACTS.mkdir(exist_ok=True)
    joblib.dump(bundle, config.ARTIFACTS / "bundle.joblib")

    # ---- the single scoring of the held-out test split ----
    s_log = best["logistic"][2].predict_proba(Xte)[:, 1]
    s_hgb = best["boosting"][2].predict_proba(Xte)[:, 1]
    s_lace = lace_df["lace"].to_numpy()[sp.test].astype(float)
    s_rand = np.zeros(len(yte))  # all tied: expected hit rate = prevalence
    # Post-hoc baseline (added after the first test run, see docs/PROTOCOL.md "Changes"):
    # rank by prior-year hospital admissions only, the strongest single input.
    s_prior = Xte["number_inpatient"].to_numpy().astype(float)
    scores = {"random": s_rand, "prior_admissions": s_prior, "lace": s_lace, "logistic": s_log, "boosting": s_hgb}
    point, paired = metrics.evaluate_scores(
        yte, scores, groups[sp.test], config.CAPACITIES, config.PRIMARY_CAPACITY,
        baselines={"lace": ["logistic", "boosting", "prior_admissions"], "prior_admissions": ["logistic", "boosting"]},
        n_resamples=n_boot, seed=config.SEED,
    )
    point["random"]["auroc_ci"] = [0.5, 0.5]

    s_dep = s_hgb if chosen == "boosting" else s_log
    risk_te = calibrator.predict(s_dep)
    calib = {
        "brier": metrics.brier(yte, risk_te),
        "brier_prevalence_only": metrics.brier(yte, np.full(len(yte), ytr.mean())),
        "mean_predicted": float(risk_te.mean()),
        "observed": float(yte.mean()),
        "bins": metrics.calibration_bins(yte, risk_te, config.CALIBRATION_BINS),
    }

    # subgroups: one shared call list (top 10% of the whole test split)
    k_cut = np.quantile(s_dep, 1 - config.PRIMARY_CAPACITY)
    called = s_dep >= k_cut
    te_raw = df.iloc[sp.test]
    group_cols = {
        "age": age_band(Xte["age_years"].to_numpy()),
        "sex": Xte["gender"].to_numpy(),
        "race": te_raw["race"].fillna("unknown").to_numpy(),
    }
    subgroups = []
    for gname, gvals in group_cols.items():
        order = ["under 60", "60-79", "80+"] if gname == "age" else sorted(set(gvals))
        for g in order:
            m = gvals == g
            npos = int(yte[m].sum())
            subgroups.append({
                "attribute": gname, "group": str(g), "n": int(m.sum()), "readmissions": npos,
                "readmission_rate": float(yte[m].mean()),
                "auroc_model": metrics.auroc(yte[m], s_dep[m]),
                "auroc_lace": metrics.auroc(yte[m], s_lace[m]),
                "share_called": float(called[m].mean()),
                "share_of_readmissions_reached": float(called[m & (yte == 1)].sum() / npos) if npos else None,
                "interpret": npos >= 50,
            })

    # worklist for the demo: random held-out encounters
    rng = np.random.default_rng(config.SEED)
    pick = rng.choice(sp.test, size=config.WORKLIST_SIZE, replace=False)
    worklist = []
    for n, i in enumerate(pick, 1):
        worklist.append({
            "id": f"T-{n:02d}",
            "encounter_id": int(df.loc[i, "encounter_id"]),
            "features": {c: (float(X.loc[i, c]) if c in data.NUMERIC else str(X.loc[i, c])) for c in data.FEATURES},
            "lace": {k: int(lace_df.loc[i, k]) for k in ("L", "A", "C", "E", "lace", "charlson")},
            "readmitted_30d": int(y[i]),
        })
    (config.ARTIFACTS / "worklist.json").write_text(json.dumps(worklist, indent=1))

    result = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "runtime_seconds": None,
        "environment": {"python": platform.python_version(), "scikit-learn": sklearn.__version__,
                        "numpy": np.__version__, "pandas": pd.__version__, "platform": platform.platform()},
        "data": {
            "source": "UCI Diabetes 130-US Hospitals for Years 1999-2008, DOI 10.24432/C5230J, CC BY 4.0",
            "sha256": _sha256(config.RAW_CSV),
            "raw_encounters": int(len(raw)),
            "after_exclusions": int(len(df)),
            "patients": int(df["patient_nbr"].nunique()),
            "splits": {
                name: {"encounters": int(len(ix)), "patients": int(len(set(groups[ix]))),
                       "readmission_rate": float(y[ix].mean())}
                for name, ix in (("train", sp.train), ("valid", sp.valid), ("test", sp.test))
            },
        },
        "config": {"seed": config.SEED, "capacities": config.CAPACITIES, "primary_capacity": config.PRIMARY_CAPACITY,
                   "minutes_per_call": config.MINUTES_PER_CALL, "bootstrap_resamples": n_boot,
                   "min_auroc_gain_for_complex_model": config.MIN_AUROC_GAIN_FOR_COMPLEX_MODEL},
        "selection": {**selection, "boosting_minus_logistic_valid_auroc": gain, "chosen": chosen, "params": params},
        "test": point,
        "paired": paired,
        "calibration": calib,
        "subgroups": subgroups,
    }
    result["runtime_seconds"] = round(time.time() - t0, 1)
    config.REPORTS.mkdir(exist_ok=True)
    (config.REPORTS / "metrics.json").write_text(json.dumps(result, indent=1))
    write_markdown(result, config.REPORTS / "EVALUATION.md")
    print(f"done in {result['runtime_seconds']} s -> reports/metrics.json, reports/EVALUATION.md")
    return result


if __name__ == "__main__":
    main()
