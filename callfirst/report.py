"""Render reports/metrics.json as reports/EVALUATION.md."""
from __future__ import annotations

NAMES = {"random": "Random order", "prior_admissions": "Prior admissions only (post-hoc)", "lace": "LACE index (baseline)", "logistic": "Logistic regression",
         "boosting": "Gradient boosting"}


def _pct(x, d=1):
    return f"{100 * x:.{d}f}%"


def _ci(c, scale=1.0, d=1):
    return f"{c[0] * scale:.{d}f}–{c[1] * scale:.{d}f}"


def write_markdown(r: dict, path) -> None:
    cfg = r["config"]
    prim = str(cfg["primary_capacity"])
    chosen = r["selection"]["chosen"]
    t = r["test"]
    d = r["data"]
    L = []
    L.append("# Evaluation results\n")
    L.append(f"Generated {r['generated']} by `python -m callfirst.train` "
             f"({cfg['bootstrap_resamples']} patient-level bootstrap resamples, seed {cfg['seed']}). "
             "Protocol: [docs/PROTOCOL.md](../docs/PROTOCOL.md).\n")
    L.append("## Data\n")
    L.append(f"{d['raw_encounters']:,} encounters → {d['after_exclusions']:,} after exclusions "
             f"({d['patients']:,} patients). SHA-256 `{d['sha256'][:16]}…`.\n")
    L.append("| Split | Encounters | Patients | 30-day readmission |")
    L.append("|---|---:|---:|---:|")
    for k, v in d["splits"].items():
        L.append(f"| {k} | {v['encounters']:,} | {v['patients']:,} | {_pct(v['readmission_rate'])} |")
    L.append("")
    L.append("## Model selection (validation split only)\n")
    sel = r["selection"]
    L.append("| Model | Setting | Validation AUROC |")
    L.append("|---|---|---:|")
    for s in sel["logistic"]:
        L.append(f"| Logistic regression | C={s['C']} | {s['valid_auroc']:.4f} |")
    for s in sel["boosting"]:
        L.append(f"| Gradient boosting | lr={s['learning_rate']}, leaves={s['max_leaf_nodes']} | {s['valid_auroc']:.4f} |")
    L.append(f"\nBoosting − logistic = {sel['boosting_minus_logistic_valid_auroc']:+.4f} "
             f"(rule: boosting only if ≥ +{cfg['min_auroc_gain_for_complex_model']}). "
             f"**Deployed: {NAMES[chosen]}**, calibrated with isotonic regression on validation.\n")

    L.append(f"## Primary result: the coordinator can call {_pct(cfg['primary_capacity'], 0)} of discharges\n")
    L.append("| Ranking | Calls | Readmissions reached per 100 calls (95% CI) | Share of all readmissions reached (95% CI) "
             f"| Nurse-hours per readmission reached* |")
    L.append("|---|---:|---:|---:|---:|")
    for name in ("random", "prior_admissions", "lace", "logistic", "boosting"):
        c = t[name]["capacity"][prim]
        hours = cfg["minutes_per_call"] * c["calls"] / max(c["readmissions_reached"], 1e-9) / 60
        L.append(f"| {NAMES[name]}{' ✔' if name == chosen else ''} | {c['calls']:,} | "
                 f"{c['per_100_calls']:.1f} ({_ci(c['per_100_calls_ci'])}) | "
                 f"{_pct(c['share_of_readmissions'])} ({_ci(c['share_of_readmissions_ci'], 100)}) | {hours:.1f} |")
    L.append(f"\n\\* Assumes {cfg['minutes_per_call']} minutes per call (stated assumption, not measured).\n")
    for b, label in (("lace", "LACE"), ("prior_admissions", "prior admissions only")):
        L.append(f"Paired difference against {label} (same bootstrap resamples):\n")
        L.append(f"| Ranking | Δ readmissions per 100 calls (95% CI) | Δ AUROC (95% CI) | Resamples where it beats {label} |")
        L.append("|---|---:|---:|---:|")
        for name, p in r["paired"][b].items():
            L.append(f"| {NAMES[name]} | {p['per_100_calls_diff']:+.1f} ({_ci(p['per_100_calls_diff_ci'])}) | "
                     f"{p['auroc_diff']:+.3f} ({_ci(p['auroc_diff_ci'], 1, 3)}) | {_pct(p['share_of_resamples_better'])} |")
        L.append("")
    L.append("## All capacities\n")
    caps = [str(c) for c in cfg["capacities"]]
    L.append("| Ranking | " + " | ".join(f"Top {_pct(float(c), 0)}: per 100 calls" for c in caps) + " | AUROC (95% CI) | AUPRC |")
    L.append("|---|" + "---:|" * (len(caps) + 2))
    for name in ("random", "prior_admissions", "lace", "logistic", "boosting"):
        cells = [f"{t[name]['capacity'][c]['per_100_calls']:.1f}" for c in caps]
        L.append(f"| {NAMES[name]} | " + " | ".join(cells) +
                 f" | {t[name]['auroc']:.3f} ({_ci(t[name]['auroc_ci'], 1, 3)}) | {t[name]['auprc']:.3f} |")
    L.append("")
    cal = r["calibration"]
    L.append("## Calibration of the deployed model (test split)\n")
    L.append(f"Brier score {cal['brier']:.4f} (predicting the training prevalence for everyone: "
             f"{cal['brier_prevalence_only']:.4f}). Mean predicted risk {_pct(cal['mean_predicted'])}, "
             f"observed {_pct(cal['observed'])}.\n")
    L.append("| Decile | Mean predicted | Observed | n |")
    L.append("|---:|---:|---:|---:|")
    for i, b in enumerate(cal["bins"], 1):
        L.append(f"| {i} | {_pct(b['mean_predicted'])} | {_pct(b['observed'])} | {b['n']:,} |")
    L.append("")
    L.append("## Subgroups (deployed model, one shared call list = top 10% of the test split)\n")
    L.append("| Attribute | Group | n | Readmissions | Rate | AUROC model | AUROC LACE | Share called | Share of group's readmissions reached |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for s in r["subgroups"]:
        flag = "" if s["interpret"] else " †"
        reached = "—" if s["share_of_readmissions_reached"] is None else _pct(s["share_of_readmissions_reached"])
        L.append(f"| {s['attribute']} | {s['group']}{flag} | {s['n']:,} | {s['readmissions']:,} | {_pct(s['readmission_rate'])} | "
                 f"{s['auroc_model']:.3f} | {s['auroc_lace']:.3f} | {_pct(s['share_called'])} | {reached} |")
    L.append("\n† Fewer than 50 readmissions: shown, not interpreted.\n")
    env = r["environment"]
    L.append(f"Environment: Python {env['python']}, scikit-learn {env['scikit-learn']}, numpy {env['numpy']}, "
             f"pandas {env['pandas']} on {env['platform']}. Runtime {r['runtime_seconds']} s.\n")
    path.write_text("\n".join(L))
