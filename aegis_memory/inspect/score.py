"""Memory Risk Score — UX sugar, clearly labeled, built from findings (never the reverse).

The score is a heuristic. Its rubric is stated inline and emitted alongside the number so
it can never sit unlabeled next to the validated benchmark. Findings are the defensible
object; this is the dopamine number for the inspect -> fix -> rescan loop.
"""

from __future__ import annotations

from .findings import Finding

# Per-severity weights (the rubric — stated, not hidden).
_WEIGHTS = {"critical": 20, "high": 12, "medium": 5, "low": 2}

# A governed/screened critical flow is materially less risky than an unscreened one.
_SCREENED_DISCOUNT = 0.25

RUBRIC = (
    "Heuristic score = min(100, sum of per-finding weights), where "
    "critical=20, high=12, medium=5, low=2. Screened (guarded) flows are discounted to "
    "25% of their weight. This is UX sugar for the fix/rescan loop, NOT the benchmark."
)


def compute_score(findings: list[Finding], *, ignore_screened: bool = False) -> dict:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    total = 0.0
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
        weight = float(_WEIGHTS.get(f.severity, 0))
        if f.screened and not ignore_screened:
            weight *= _SCREENED_DISCOUNT
        total += weight
    score = min(100, round(total))
    return {
        "score": score,
        "max": 100,
        "label": "heuristic",
        "rubric": RUBRIC,
        "counts": counts,
    }


def raw_score(findings: list[Finding]) -> int:
    """The before-screening exposure: the same heuristic with every flow counted at full
    weight (screening discounts ignored). Used as the generic in-run ``before`` so any project
    gets an honest before -> after transition without needing a second (unscreened) package."""
    return compute_score(findings, ignore_screened=True)["score"]
