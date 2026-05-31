"""Confusion-matrix metrics, bootstrap CIs, and the Aegis stage ablation.

A metric is reported as ``None`` when its denominator is zero at the full-sample
level (e.g. FPR on a malicious-only dataset, which has no negatives) — that is
more honest than reporting a misleading ``0.0``.
"""

from __future__ import annotations

import numpy as np

N_BOOTSTRAP = 1000
BOOTSTRAP_SEED = 42


# --------------------------------------------------------------------------
# Point metrics
# --------------------------------------------------------------------------
def confusion(y_true: list[bool], y_pred: list[bool]) -> dict[str, int]:
    tp = fp = tn = fn = 0
    for yt, yp in zip(y_true, y_pred):
        if yt and yp:
            tp += 1
        elif (not yt) and yp:
            fp += 1
        elif (not yt) and (not yp):
            tn += 1
        else:
            fn += 1
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}


def _div(num: float, den: float) -> float | None:
    return None if den == 0 else num / den


def point_metrics(c: dict[str, int]) -> dict[str, float | None]:
    tp, fp, tn, fn = c["tp"], c["fp"], c["tn"], c["fn"]
    precision = _div(tp, tp + fp)
    recall = _div(tp, tp + fn)
    fpr = _div(fp, fp + tn)
    total = tp + fp + tn + fn
    accuracy = _div(tp + tn, total)
    if precision is None or recall is None or (precision + recall) == 0:
        f1 = None if (precision is None or recall is None) else 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return {"precision": precision, "recall": recall, "f1": f1,
            "fpr": fpr, "accuracy": accuracy}


# --------------------------------------------------------------------------
# Bootstrap confidence intervals
# --------------------------------------------------------------------------
def _metric_from_arrays(yt: np.ndarray, yp: np.ndarray, which: str) -> float | None:
    tp = int(np.sum(yt & yp))
    fp = int(np.sum(~yt & yp))
    tn = int(np.sum(~yt & ~yp))
    fn = int(np.sum(yt & ~yp))
    m = point_metrics({"tp": tp, "fp": fp, "tn": tn, "fn": fn})
    return m[which]


def bootstrap_cis(
    y_true: list[bool], y_pred: list[bool],
    n_bootstrap: int = N_BOOTSTRAP, seed: int = BOOTSTRAP_SEED,
) -> dict[str, list[float] | None]:
    """95% percentile CIs for precision/recall/f1/fpr via case resampling."""
    yt = np.asarray(y_true, dtype=bool)
    yp = np.asarray(y_pred, dtype=bool)
    n = len(yt)
    rng = np.random.default_rng(seed)
    out: dict[str, list[float] | None] = {}
    for which in ("precision", "recall", "f1", "fpr"):
        # If undefined on the full sample, don't fabricate a CI.
        if _metric_from_arrays(yt, yp, which) is None:
            out[which] = None
            continue
        vals: list[float] = []
        for _ in range(n_bootstrap):
            idx = rng.integers(0, n, n)
            v = _metric_from_arrays(yt[idx], yp[idx], which)
            if v is not None:
                vals.append(v)
        if vals:
            lo, hi = np.percentile(vals, [2.5, 97.5])
            out[which] = [float(lo), float(hi)]
        else:
            out[which] = None
    return out


# --------------------------------------------------------------------------
# Full per-(system, dataset) result
# --------------------------------------------------------------------------
def evaluate_run(
    y_true: list[bool], y_pred: list[bool], latencies_ms: list[float],
) -> dict:
    c = confusion(y_true, y_pred)
    pm = point_metrics(c)
    result = {
        "n": len(y_true),
        "confusion": c,
        **pm,
        "median_latency_ms": (float(np.median(latencies_ms)) if latencies_ms else None),
        "ci95": bootstrap_cis(y_true, y_pred),
    }
    return result


# --------------------------------------------------------------------------
# Aegis stage ablation
# --------------------------------------------------------------------------
def stage_ablation(
    y_true: list[bool], stage_records: list[dict[int, bool]],
) -> list[dict]:
    """Cumulative Stage 1 -> +2 -> +3 -> +4 metrics.

    ``stage_records[i]`` is ``{1..4 -> fired?}`` for item ``i``.
    Returns one row per cumulative stage set with full metrics + CIs.
    """
    cumulative = {
        "stage_1": [1],
        "stage_1_2": [1, 2],
        "stage_1_2_3": [1, 2, 3],
        "stage_1_2_3_4": [1, 2, 3, 4],
    }
    rows = []
    for label, stages in cumulative.items():
        y_pred = [any(rec.get(s, False) for s in stages) for rec in stage_records]
        c = confusion(y_true, y_pred)
        pm = point_metrics(c)
        rows.append({
            "stages": label,
            "confusion": c,
            "recall": pm["recall"],
            "fpr": pm["fpr"],
            "precision": pm["precision"],
            "f1": pm["f1"],
            "accuracy": pm["accuracy"],
            "ci95": bootstrap_cis(y_true, y_pred),
        })
    return rows


def marginal_stage_contribution(stage_records: list[dict[int, bool]]) -> dict[int, int]:
    """How many items each stage flagged *alone* (any flag from that stage)."""
    counts = {1: 0, 2: 0, 3: 0, 4: 0}
    for rec in stage_records:
        for s in (1, 2, 3, 4):
            if rec.get(s, False):
                counts[s] += 1
    return counts
