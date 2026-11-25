import numpy as np
import pytest
from sklearn.metrics import roc_auc_score

from callfirst import careplan, config, lace, metrics
from callfirst.data import icd9_group


def test_los_points():
    assert [lace.los_points(d) for d in (0, 1, 2, 3, 4, 6, 7, 13, 14, 20)] == [0, 1, 2, 3, 4, 4, 5, 5, 7, 7]


def test_charlson_diabetes_baseline_and_supersede():
    assert lace.charlson_index([None, None, None]) == 1           # diabetic encounter by inclusion
    assert lace.charlson_index(["250.4", None, None]) == 2        # complicated replaces uncomplicated
    assert lace.charlson_index(["428", "410", "V45"]) == 3        # CHF + MI + diabetes; V codes ignored
    assert lace.charlson_index(["197", "174", None]) == 7         # metastatic (6) replaces malignancy, + diabetes


def test_icd9_groups():
    assert icd9_group("428") == "circulatory"
    assert icd9_group("250.83") == "diabetes"
    assert icd9_group("786") == "respiratory"
    assert icd9_group("V57") == "other"
    assert icd9_group(np.nan) == "missing"


def test_auroc_matches_sklearn_with_ties():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 500)
    s = rng.integers(0, 5, 500).astype(float)
    assert metrics.auroc(y, s) == pytest.approx(roc_auc_score(y, s))


def test_capacity_ties_use_expected_value():
    y = np.array([1, 0, 1, 0, 0, 0])
    s = np.array([3, 2, 2, 2, 2, 1.0])
    hits, k = metrics.capacity_hits(y, s, 0.5)    # k=3: one above, 2 of 4 tied slots, tied rate 1/4
    assert k == 3
    assert hits == pytest.approx(1 + 2 * 0.25)
    # order of rows does not change the answer
    p = np.array([5, 4, 3, 2, 1, 0])
    assert metrics.capacity_hits(y[p], s[p], 0.5)[0] == pytest.approx(hits)


def test_cluster_bootstrap_keeps_patients_together():
    groups = np.array([7, 7, 3, 9, 9, 9])
    boot = metrics.ClusterBootstrap(groups, n_resamples=50, seed=1)
    for idx in boot.indices():
        sampled = groups[idx]
        for g in set(sampled):
            # every sampled patient brings all of their encounters (a multiple of their count)
            assert (sampled == g).sum() % (groups == g).sum() == 0


def _features(**kw):
    base = {"discharge_to": "home", "number_inpatient": 0, "number_emergency": 0, "n_dose_changes": 0,
            "med_change": "no", "num_medications": 10, "insulin": "no", "a1c": "not measured",
            "max_glu": "not measured", "age_years": 65}
    base.update(kw)
    return base


def test_checklist_rules():
    ids = lambda items: [i["id"] for i in items]
    assert ids(careplan.checklist(_features(), in_call_list=False)) == []
    assert ids(careplan.checklist(_features(), in_call_list=True)) == ["call"]
    items = careplan.checklist(_features(number_inpatient=2, insulin="up", n_dose_changes=1, med_change="yes",
                                         a1c=">8", age_years=85), in_call_list=True)
    assert ids(items) == ["call", "visit", "meds", "glucose", "home"]
    assert "insulin dose went up" in items[2]["why"]
    assert ids(careplan.checklist(_features(discharge_to="nursing facility"), in_call_list=True)) == ["handoff"]
    assert ids(careplan.checklist(_features(discharge_to="left against advice"), in_call_list=False)) == ["ama"]
    for it in items:
        assert it["source"] in careplan.SOURCES


needs_model = pytest.mark.skipif(not (config.ARTIFACTS / "bundle.joblib").exists(),
                                 reason="run `python -m callfirst.train` first")


@needs_model
def test_api():
    from fastapi.testclient import TestClient

    from callfirst.app import app
    c = TestClient(app)
    assert c.get("/").status_code == 200
    meta = c.get("/api/meta").json()
    assert "Not a medical device" in meta["disclaimer"] or "not a medical device" in meta["disclaimer"]
    rows = c.get("/api/worklist").json()
    assert len(rows) == config.WORKLIST_SIZE
    assert all(0 <= r["risk"] <= 1 for r in rows)
    r = c.post("/api/score", json={"features": {"number_inpatient": 4}}).json()
    low = c.post("/api/score", json={"features": {"number_inpatient": 0}}).json()
    assert r["risk"] > low["risk"]
    assert r["factors"][0]["feature"] == "number_inpatient"
    assert c.post("/api/score", json={"features": {"nope": 1}}).status_code == 422
    assert c.post("/api/score", json={"features": {"gender": "x"}}).status_code == 422
    assert c.post("/api/score", json={"features": {"number_inpatient": -3}}).status_code == 422


@needs_model
def test_split_has_no_patient_overlap():
    from callfirst import data
    df = data.clean(data.load_raw())
    sp = data.split_by_patient(df)
    g = df["patient_nbr"].to_numpy()
    assert not set(g[sp.train]) & set(g[sp.test])
    assert not set(g[sp.valid]) & set(g[sp.test])
    assert len(sp.train) + len(sp.valid) + len(sp.test) == len(df)
