"""Per-patient explanation: how much each input moves this patient's score.

For each input we replace the patient's value with the typical value in the training data
(median for numbers, most common category) and re-score. The change, in percentage points of
the model score, is that input's contribution. Works for any model; it is a local what-if,
not a causal claim.
"""
from __future__ import annotations

import pandas as pd

from .data import FEATURE_LABELS, FEATURES


def _fmt(feature: str, value) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if feature == "age_years":
        return f"{int(value) - 5}-{int(value) + 4}"
    if feature == "time_in_hospital":
        return f"{value} days"
    return str(value)


def contributions(bundle, row: pd.DataFrame, top: int = 4) -> list[dict]:
    base = float(bundle.score(row)[0])
    variants = []
    names = []
    for f in FEATURES:
        if str(row.iloc[0][f]) == str(bundle.reference[f]):
            continue
        r = row.copy()
        r[f] = bundle.reference[f]
        variants.append(r)
        names.append(f)
    if not variants:
        return []
    scores = bundle.score(pd.concat(variants, ignore_index=True))
    out = []
    for f, s in zip(names, scores):
        delta = 100 * (base - float(s))
        out.append({
            "feature": f,
            "label": FEATURE_LABELS[f],
            "value": _fmt(f, row.iloc[0][f]),
            "typical": _fmt(f, bundle.reference[f]),
            "points": round(delta, 1),
        })
    out.sort(key=lambda d: -abs(d["points"]))
    return [d for d in out if abs(d["points"]) >= 0.1][:top]
