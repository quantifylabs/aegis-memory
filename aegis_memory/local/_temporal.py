"""
Temporal decay for Aegis Memory local mode.

Port of server/temporal_decay.py — same math, no server imports.

Formula:
    decay_factor = exp(-λ × age_days)
    λ = ln(2) / half_life_days
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

# Half-life in days per memory type
HALF_LIVES: dict[str, int] = {
    "episodic": 7,
    "progress": 14,
    "feature": 14,
    "standard": 30,
    "reflection": 60,
    "strategy": 90,
    "semantic": 90,
    "procedural": 180,
    "control": 180,
}
DEFAULT_HALF_LIFE = 30


def compute_decay_factor(
    memory_type: str,
    created_at: datetime,
    last_accessed_at: datetime | None,
    now: datetime | None = None,
) -> float:
    """
    Returns decay factor in (0, 1].

    1.0 means just accessed (age=0), approaches 0 with age.
    """
    now = now or datetime.now(timezone.utc)
    half_life = HALF_LIVES.get(memory_type, DEFAULT_HALF_LIFE)
    reference = last_accessed_at or created_at

    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    age_days = max(0.0, (now - reference).total_seconds() / 86400)
    lam = math.log(2) / half_life
    return math.exp(-lam * age_days)


def rerank_with_decay(
    results: list[tuple],
    now: datetime | None = None,
) -> list[tuple]:
    """
    Re-sort (memory_dict, semantic_score) by semantic_score × decay_factor desc.

    memory_dict must have 'memory_type', 'created_at', and optionally 'last_accessed_at'.

    Returns [(memory_dict, semantic_score, decay_factor), ...] sorted desc.
    """
    from datetime import datetime as dt

    now = now or datetime.now(timezone.utc)
    scored = []
    for mem, sem_score in results:
        created = mem.get("created_at")
        if isinstance(created, str):
            created = dt.fromisoformat(created.replace("Z", "+00:00"))
        last_acc = mem.get("last_accessed_at")
        if isinstance(last_acc, str):
            last_acc = dt.fromisoformat(last_acc.replace("Z", "+00:00"))

        decay = compute_decay_factor(
            mem.get("memory_type", "standard"),
            created,
            last_acc,
            now,
        )
        scored.append((mem, sem_score, decay, sem_score * decay))
    scored.sort(key=lambda x: x[3], reverse=True)
    return [(mem, sem, decay) for mem, sem, decay, _ in scored]
