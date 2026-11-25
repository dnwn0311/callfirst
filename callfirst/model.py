"""Model pipelines, calibration, and the frozen bundle used by the demo."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from .data import CATEGORICAL, FEATURES, NUMERIC


def _preprocessor(scale: bool) -> ColumnTransformer:
    num = make_pipeline(FunctionTransformer(np.log1p, feature_names_out="one-to-one"), StandardScaler()) if scale \
        else "passthrough"
    cat = OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=50, sparse_output=False)
    return ColumnTransformer([("num", num, NUMERIC), ("cat", cat, CATEGORICAL)])


def logistic(C: float, seed: int) -> Pipeline:
    return Pipeline([
        ("prep", _preprocessor(scale=True)),
        ("clf", LogisticRegression(C=C, max_iter=2000, random_state=seed)),
    ])


def boosting(params: dict, seed: int) -> Pipeline:
    return Pipeline([
        ("prep", _preprocessor(scale=False)),
        ("clf", HistGradientBoostingClassifier(random_state=seed, early_stopping=False, **params)),
    ])


@dataclass
class Bundle:
    """Everything the demo needs, frozen after validation."""
    name: str
    params: dict
    pipeline: Pipeline
    calibrator: IsotonicRegression
    reference: dict                      # per-feature reference value (train median / mode)
    valid_scores: np.ndarray             # uncalibrated validation scores, for percentiles
    lace_risk: dict                      # LACE score -> observed 30-day readmission rate (train+valid)
    options: dict = field(default_factory=dict)   # categorical options for the form

    def score(self, X: pd.DataFrame) -> np.ndarray:
        return self.pipeline.predict_proba(X[FEATURES])[:, 1]

    def risk(self, X: pd.DataFrame) -> np.ndarray:
        return self.calibrator.predict(self.score(X))

    def percentile(self, scores: np.ndarray) -> np.ndarray:
        """Share of validation discharges with a lower score (0-100)."""
        v = np.sort(self.valid_scores)
        return 100 * np.searchsorted(v, scores, side="left") / len(v)

    def top_fraction_cutoff(self, frac: float) -> float:
        return float(np.quantile(self.valid_scores, 1 - frac))


def reference_values(X: pd.DataFrame) -> dict:
    ref = {}
    for c in NUMERIC:
        ref[c] = float(X[c].median())
    for c in CATEGORICAL:
        ref[c] = str(X[c].mode().iloc[0])
    return ref


def fill_defaults(partial: dict, reference: dict) -> pd.DataFrame:
    row = {c: partial.get(c, reference[c]) for c in FEATURES}
    for c in NUMERIC:
        row[c] = float(row[c])
    for c in CATEGORICAL:
        row[c] = str(row[c])
    return pd.DataFrame([row], columns=FEATURES)
