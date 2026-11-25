"""Every number that affects the evaluation lives here (see docs/PROTOCOL.md)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_CSV = ROOT / "data" / "raw" / "diabetic_data.csv"
ARTIFACTS = ROOT / "artifacts"          # trained model (not committed, rebuilt by `python -m callfirst.train`)
REPORTS = ROOT / "reports"              # metrics.json + EVALUATION.md (committed)

SEED = 20261204

# Split by patient_nbr so that no patient appears in more than one split.
TEST_FRACTION = 0.20
VALID_FRACTION = 0.20   # of all patients; the rest (60%) is training

# Strack et al. 2014 removed encounters ending in death or hospice: no readmission is possible
# or follow-up calls are not the right intervention.
EXCLUDED_DISCHARGE_IDS = {11, 13, 14, 19, 20, 21}

LABEL_VALUE = "<30"   # readmitted within 30 days

# Model choice is decided on the validation split only.
# Logistic regression is preferred (simpler, easier to audit) unless gradient boosting beats it
# by at least this much validation AUROC.
MIN_AUROC_GAIN_FOR_COMPLEX_MODEL = 0.01
LOGREG_C_GRID = [0.01, 0.1, 1.0]
HGB_GRID = [
    {"learning_rate": lr, "max_leaf_nodes": leaves, "max_iter": 300, "min_samples_leaf": 40}
    for lr in (0.05, 0.1)
    for leaves in (15, 31)
]

# "A care coordinator can call k% of today's discharges."
CAPACITIES = [0.05, 0.10, 0.20, 0.30]
PRIMARY_CAPACITY = 0.10
MINUTES_PER_CALL = 20   # stated assumption: AHRQ RED Tool 5 says calls take about 20-60 minutes; we use the low end

BOOTSTRAP_RESAMPLES = 2000   # clustered by patient
CALIBRATION_BINS = 10

# Rows shown in the demo worklist: a random sample of held-out test encounters.
WORKLIST_SIZE = 24
