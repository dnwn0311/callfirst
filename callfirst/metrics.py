"""Metrics with patient-clustered bootstrap confidence intervals."""
from __future__ import annotations

import numpy as np
from scipy.stats import rankdata
from sklearn.metrics import average_precision_score


def auroc(y: np.ndarray, s: np.ndarray) -> float:
    """Mann-Whitney AUROC with average ranks for ties."""
    y = np.asarray(y)
    n1 = y.sum()
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = rankdata(s)
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def capacity_hits(y: np.ndarray, s: np.ndarray, frac: float) -> tuple[float, int]:
    """Expected readmissions reached when calling the top `frac` of patients ranked by s.

    Ties at the cut-off contribute their average outcome, so the result does not depend on row order.
    Returns (expected hits, number of calls).
    """
    n = len(y)
    k = int(round(frac * n))
    if k == 0:
        return 0.0, 0
    order = np.argsort(-s, kind="stable")
    t = s[order[k - 1]]
    above = s > t
    tied = s == t
    n_above = int(above.sum())
    hits = y[above].sum() + (k - n_above) * y[tied].mean()
    return float(hits), k


def ppv_at(y, s, frac):
    hits, k = capacity_hits(y, s, frac)
    return hits / k if k else float("nan")


def recall_at(y, s, frac):
    hits, _ = capacity_hits(y, s, frac)
    pos = y.sum()
    return hits / pos if pos else float("nan")


def brier(y, p):
    return float(np.mean((p - y) ** 2))


def calibration_bins(y, p, n_bins=10):
    order = np.argsort(p, kind="stable")
    bins = np.array_split(order, n_bins)
    return [
        {"mean_predicted": float(p[b].mean()), "observed": float(y[b].mean()), "n": int(len(b))}
        for b in bins
    ]


class ClusterBootstrap:
    """Resample patients with replacement; all encounters of a sampled patient come along."""

    def __init__(self, groups: np.ndarray, n_resamples: int, seed: int):
        order = np.argsort(groups, kind="stable")
        sorted_groups = groups[order]
        starts = np.flatnonzero(np.r_[True, sorted_groups[1:] != sorted_groups[:-1]])
        self.order = order
        self.starts = starts
        self.counts = np.diff(np.r_[starts, len(groups)])
        self.n_groups = len(starts)
        self.n_resamples = n_resamples
        self.rng = np.random.default_rng(seed)

    def indices(self):
        for _ in range(self.n_resamples):
            g = self.rng.integers(0, self.n_groups, self.n_groups)
            c = self.counts[g]
            total = c.sum()
            offsets = np.arange(total) - np.repeat(np.cumsum(c) - c, c)
            yield self.order[np.repeat(self.starts[g], c) + offsets]


def ci(values, alpha=0.05):
    v = np.asarray(values, dtype=float)
    v = v[~np.isnan(v)]
    return [float(np.quantile(v, alpha / 2)), float(np.quantile(v, 1 - alpha / 2))]


def evaluate_scores(y, scores: dict[str, np.ndarray], groups, capacities, primary, baselines, n_resamples, seed):
    """Point estimates and clustered-bootstrap CIs for each scorer, plus paired differences vs each baseline.

    `baselines` maps a baseline name to the scorers compared against it.
    """
    y = np.asarray(y)
    names = list(scores)
    point = {}
    for name in names:
        s = scores[name]
        point[name] = {
            "auroc": auroc(y, s),
            "auprc": float(average_precision_score(y, s)),
            "capacity": {
                str(f): {"calls": capacity_hits(y, s, f)[1], "readmissions_reached": capacity_hits(y, s, f)[0],
                         "per_100_calls": 100 * ppv_at(y, s, f), "share_of_readmissions": recall_at(y, s, f)}
                for f in capacities
            },
        }

    boot = {name: {"auroc": [], **{f"ppv_{f}": [] for f in capacities}, **{f"recall_{f}": [] for f in capacities}}
            for name in names}
    pairs = [(name, b) for b, others in baselines.items() for name in others]
    diffs = {pair: {"auroc": [], "per_100_calls_primary": []} for pair in pairs}
    for idx in ClusterBootstrap(np.asarray(groups), n_resamples, seed).indices():
        yb = y[idx]
        per = {}
        for name in names:
            sb = scores[name][idx]
            a = auroc(yb, sb)
            boot[name]["auroc"].append(a)
            for f in capacities:
                boot[name][f"ppv_{f}"].append(100 * ppv_at(yb, sb, f))
                boot[name][f"recall_{f}"].append(recall_at(yb, sb, f))
            per[name] = (a, 100 * ppv_at(yb, sb, primary))
        for name, b in diffs:
            diffs[(name, b)]["auroc"].append(per[name][0] - per[b][0])
            diffs[(name, b)]["per_100_calls_primary"].append(per[name][1] - per[b][1])

    for name in names:
        point[name]["auroc_ci"] = ci(boot[name]["auroc"])
        for f in capacities:
            point[name]["capacity"][str(f)]["per_100_calls_ci"] = ci(boot[name][f"ppv_{f}"])
            point[name]["capacity"][str(f)]["share_of_readmissions_ci"] = ci(boot[name][f"recall_{f}"])
    paired = {}
    for (name, b), d in diffs.items():
        a = np.asarray(d["auroc"])
        p = np.asarray(d["per_100_calls_primary"])
        paired.setdefault(b, {})[name] = {
            "auroc_diff": point[name]["auroc"] - point[b]["auroc"],
            "auroc_diff_ci": ci(a),
            "per_100_calls_diff": 100 * (ppv_at(y, scores[name], primary) - ppv_at(y, scores[b], primary)),
            "per_100_calls_diff_ci": ci(p),
            "share_of_resamples_better": float(np.mean(p > 0)),
        }
    return point, paired
