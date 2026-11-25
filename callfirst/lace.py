"""LACE index (van Walraven et al., CMAJ 2010), approximated from the fields in this dataset.

L  length of stay in days            <1:0, 1:1, 2:2, 3:3, 4-6:4, 7-13:5, >=14:7
A  acute (emergent) admission         3
C  Charlson comorbidity index         0:0, 1:1, 2:2, 3:3, >=4:5
E  emergency visits                   0..3 as is, >=4:4

Approximations (stated in docs/PROTOCOL.md):
- Charlson uses only the three diagnoses recorded per encounter, mostly at 3-digit ICD-9 precision.
- Every encounter in the dataset is a diabetic encounter, so everyone gets at least the
  uncomplicated-diabetes point.
- E uses the prior-year ER visit count; LACE defines it over the prior 6 months.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# (weight, list of (low, high) numeric ICD-9 ranges, inclusive low, exclusive high)
CHARLSON = {
    "myocardial_infarction": (1, [(410, 411), (412, 413)]),
    "heart_failure": (1, [(428, 429), (425.4, 426)]),
    "peripheral_vascular": (1, [(440, 442), (443.9, 444), (785.4, 785.5)]),
    "cerebrovascular": (1, [(430, 439)]),
    "dementia": (1, [(290, 291), (294.1, 294.2), (331.2, 331.3)]),
    "chronic_pulmonary": (1, [(490, 497), (500, 506), (506.4, 506.5)]),
    "rheumatic": (1, [(710.0, 710.2), (710.4, 710.5), (714.0, 714.3), (714.8, 714.9), (725, 726)]),
    "peptic_ulcer": (1, [(531, 535)]),
    "mild_liver": (1, [(571, 572)]),
    "diabetes_complicated": (2, [(250.4, 250.7)]),
    "hemiplegia": (2, [(342, 343), (344, 345)]),
    "renal": (2, [(582, 583.8), (585, 587), (588, 589)]),
    "malignancy": (2, [(140, 173), (174, 196), (200, 209)]),
    "severe_liver": (3, [(456.0, 456.3), (572.2, 572.9)]),
    "metastatic": (6, [(196, 200)]),
    "hiv_aids": (6, [(42, 45)]),
}
# A more severe category replaces its milder form.
SUPERSEDES = {"diabetes_complicated": "diabetes", "severe_liver": "mild_liver", "metastatic": "malignancy"}


def _numeric(code) -> float | None:
    if code is None or (isinstance(code, float) and np.isnan(code)):
        return None
    s = str(code)
    if not s or s[0] in "E":
        return None
    if s[0] == "V":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def charlson_index(codes) -> int:
    found = {"diabetes": 1}  # diabetic encounter by inclusion criteria
    for code in codes:
        v = _numeric(code)
        if v is None:
            continue
        for name, (weight, ranges) in CHARLSON.items():
            if any(lo <= v < hi for lo, hi in ranges):
                found[name] = weight
    for severe, mild in SUPERSEDES.items():
        if severe in found:
            found.pop(mild, None)
    return int(sum(found.values()))


def los_points(days: float) -> int:
    d = int(days)
    if d < 1:
        return 0
    if d <= 3:
        return d
    if d <= 6:
        return 4
    if d <= 13:
        return 5
    return 7


def comorbidity_points(cci: int) -> int:
    return cci if cci <= 3 else 5


def lace_components(df: pd.DataFrame) -> pd.DataFrame:
    """df is the cleaned raw table (needs time_in_hospital, admission ids, diag_1..3, number_emergency)."""
    L = df["time_in_hospital"].map(los_points)
    acute = df["admission_type_id"].isin([1, 7]) | (df["admission_source_id"] == 7)
    A = np.where(acute, 3, 0)
    cci = [charlson_index(row) for row in df[["diag_1", "diag_2", "diag_3"]].itertuples(index=False)]
    C = pd.Series(cci, index=df.index).map(comorbidity_points)
    E = df["number_emergency"].clip(upper=4)
    out = pd.DataFrame({"L": L, "A": A, "C": C, "E": E}, index=df.index)
    out["charlson"] = cci
    out["lace"] = out[["L", "A", "C", "E"]].sum(axis=1)
    return out
