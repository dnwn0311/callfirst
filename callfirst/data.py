"""Load the UCI diabetes readmission data, clean it, build features, split by patient."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

from . import config

DIABETES_MEDS = [
    "metformin", "repaglinide", "nateglinide", "chlorpropamide", "glimepiride", "acetohexamide",
    "glipizide", "glyburide", "tolbutamide", "pioglitazone", "rosiglitazone", "acarbose", "miglitol",
    "troglitazone", "tolazamide", "examide", "citoglipton", "insulin", "glyburide-metformin",
    "glipizide-metformin", "glimepiride-pioglitazone", "metformin-rosiglitazone", "metformin-pioglitazone",
]

NUMERIC = [
    "age_years", "time_in_hospital", "num_lab_procedures", "num_procedures", "num_medications",
    "number_outpatient", "number_emergency", "number_inpatient", "number_diagnoses",
    "n_diabetes_meds", "n_dose_changes",
]
CATEGORICAL = [
    "gender", "admission_type", "admission_source", "discharge_to", "specialty",
    "diag_1_group", "diag_2_group", "diag_3_group", "a1c", "max_glu", "insulin", "metformin",
    "med_change", "diabetes_med",
]
FEATURES = NUMERIC + CATEGORICAL

# Human-readable names, used by the explanation and the UI.
FEATURE_LABELS = {
    "age_years": "Age",
    "time_in_hospital": "Length of stay",
    "num_lab_procedures": "Lab tests this stay",
    "num_procedures": "Procedures this stay",
    "num_medications": "Medications this stay",
    "number_outpatient": "Outpatient visits, past year",
    "number_emergency": "ER visits, past year",
    "number_inpatient": "Hospital admissions, past year",
    "number_diagnoses": "Number of diagnoses",
    "n_diabetes_meds": "Diabetes medicines",
    "n_dose_changes": "Diabetes dose changes",
    "gender": "Sex",
    "admission_type": "Admission type",
    "admission_source": "Admitted from",
    "discharge_to": "Discharged to",
    "specialty": "Admitting specialty",
    "diag_1_group": "Main diagnosis",
    "diag_2_group": "Second diagnosis",
    "diag_3_group": "Third diagnosis",
    "a1c": "HbA1c result",
    "max_glu": "Max glucose result",
    "insulin": "Insulin",
    "metformin": "Metformin",
    "med_change": "Any diabetes medicine changed",
    "diabetes_med": "On diabetes medicine",
}


def _admission_type(i: int) -> str:
    return {1: "emergency", 7: "emergency", 2: "urgent", 3: "elective"}.get(int(i), "other/unknown")


def _admission_source(i: int) -> str:
    i = int(i)
    if i == 7:
        return "emergency room"
    if i in (1, 2, 3):
        return "referral"
    if i in (4, 5, 6, 10, 18, 19, 22, 25, 26):
        return "transfer"
    return "other/unknown"


def _discharge_to(i: int) -> str:
    i = int(i)
    if i == 1:
        return "home"
    if i in (6, 8):
        return "home with home health"
    if i in (3, 4, 24):
        return "nursing facility"
    if i == 7:
        return "left against advice"
    if i in (2, 5, 9, 10, 15, 16, 17, 22, 23, 27, 28, 29, 30):
        return "other facility"
    return "other/unknown"


TOP_SPECIALTIES = [
    "InternalMedicine", "Emergency/Trauma", "Family/GeneralPractice", "Cardiology",
    "Surgery-General", "Nephrology", "Orthopedics", "Orthopedics-Reconstructive", "Radiologist",
    "Pulmonology",
]


def icd9_group(code) -> str:
    """ICD-9 chapter groups used by Strack et al. 2014 (Table 2)."""
    if code is None or (isinstance(code, float) and np.isnan(code)) or code == "":
        return "missing"
    s = str(code)
    if s[0] in "VE":
        return "other"
    v = float(s)
    if 250 <= v < 251:
        return "diabetes"
    if 390 <= v < 460 or int(v) == 785:
        return "circulatory"
    if 460 <= v < 520 or int(v) == 786:
        return "respiratory"
    if 520 <= v < 580 or int(v) == 787:
        return "digestive"
    if 800 <= v < 1000:
        return "injury"
    if 710 <= v < 740:
        return "musculoskeletal"
    if 580 <= v < 630 or int(v) == 788:
        return "genitourinary"
    if 140 <= v < 240:
        return "neoplasms"
    return "other"


def load_raw(path=config.RAW_CSV) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run: python scripts/download_data.py")
    return pd.read_csv(path, na_values="?", low_memory=False, dtype={"diag_1": str, "diag_2": str, "diag_3": str})


def clean(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw[~raw["discharge_disposition_id"].isin(config.EXCLUDED_DISCHARGE_IDS)]
    df = df[df["gender"].isin(["Female", "Male"])].copy()
    df["y"] = (df["readmitted"] == config.LABEL_VALUE).astype(int)
    return df.reset_index(drop=True)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return the model input table (one row per encounter, columns = FEATURES)."""
    out = pd.DataFrame(index=df.index)
    out["age_years"] = df["age"].str.extract(r"\[(\d+)-")[0].astype(float) + 5
    for col in ["time_in_hospital", "num_lab_procedures", "num_procedures", "num_medications",
                "number_outpatient", "number_emergency", "number_inpatient", "number_diagnoses"]:
        out[col] = df[col].astype(float)
    meds = df[DIABETES_MEDS]
    out["n_diabetes_meds"] = (meds != "No").sum(axis=1).astype(float)
    out["n_dose_changes"] = meds.isin(["Up", "Down"]).sum(axis=1).astype(float)

    out["gender"] = df["gender"].str.lower()
    out["admission_type"] = df["admission_type_id"].map(_admission_type)
    out["admission_source"] = df["admission_source_id"].map(_admission_source)
    out["discharge_to"] = df["discharge_disposition_id"].map(_discharge_to)
    spec = df["medical_specialty"]
    out["specialty"] = np.where(spec.isna(), "missing", np.where(spec.isin(TOP_SPECIALTIES), spec, "other"))
    for i in (1, 2, 3):
        out[f"diag_{i}_group"] = df[f"diag_{i}"].map(icd9_group)
    out["a1c"] = df["A1Cresult"].fillna("not measured")
    out["max_glu"] = df["max_glu_serum"].fillna("not measured")
    out["insulin"] = df["insulin"].str.lower()
    out["metformin"] = df["metformin"].str.lower()
    out["med_change"] = np.where(df["change"] == "Ch", "yes", "no")
    out["diabetes_med"] = df["diabetesMed"].str.lower()
    return out[FEATURES]


@dataclass
class Split:
    train: np.ndarray
    valid: np.ndarray
    test: np.ndarray


def split_by_patient(df: pd.DataFrame, seed: int = config.SEED) -> Split:
    groups = df["patient_nbr"].to_numpy()
    idx = np.arange(len(df))
    outer = GroupShuffleSplit(n_splits=1, test_size=config.TEST_FRACTION, random_state=seed)
    trval, test = next(outer.split(idx, groups=groups))
    inner_size = config.VALID_FRACTION / (1 - config.TEST_FRACTION)
    inner = GroupShuffleSplit(n_splits=1, test_size=inner_size, random_state=seed + 1)
    tr, va = next(inner.split(trval, groups=groups[trval]))
    return Split(train=trval[tr], valid=trval[va], test=test)
