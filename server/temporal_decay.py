"""
Temporal Decay Engine for Aegis Memory (Priority 4)

Implements time-based relevance decay so memories that haven't been accessed
recently lose ranking weight during retrieval.

Formula (roadmap-faithful):
    decay_factor      = exp(-λ × age_days)
    age_days          = (now - last_accessed_at) ?? (now - created_at)
    λ                 = ln(2) / half_life_days   (per memory type)
    relevance_score   = effectiveness_score × decay_factor

Re-ranking when apply_decay=True:
    final_ranking_score = semantic_score × decay_factor
Results are re-sorted by final_ranking_score after pgvector returns candidates.
"""

import math
from datetime import datetime, timezone

# Half-life in days per memory type.
# Higher = decays slower (more durable memory type).
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

    - 1.0 means just accessed (age = 0)
    - Approaches 0 as age grows relative to the type's half-life
    - Uses last_accessed_at if available, otherwise falls back to created_at
    """
    now = now or datetime.now(timezone.utc)
    half_life = HALF_LIVES.get(memory_type, DEFAULT_HALF_LIFE)
    reference = last_accessed_at or created_at

    # Ensure reference is timezone-aware for comparison
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    age_days = max(0.0, (now - reference).total_seconds() / 86400)
    lam = math.log(2) / half_life
    return math.exp(-lam * age_days)


def compute_relevance_score(mem: object, now: datetime | None = None) -> float:
    """
    Roadmap formula: effectiveness_score × decay_factor.

    Combines vote-based quality with temporal freshness into a single
    relevance score surfaced on every query response.
    """
    decay = compute_decay_factor(
        mem.memory_type,
        mem.created_at,
        mem.last_accessed_at,
        now,
    )
    return mem.get_effectiveness_score() * decay


def rerank_with_decay(
    results: list[tuple],
    now: datetime | None = None,
) -> list[tuple]:
    """
    Re-sort (mem, semantic_score) list by semantic_score × decay_factor desc.

    Returns list of (mem, semantic_score, decay_factor) tuples, sorted by
    final_ranking_score = semantic_score × decay_factor descending.

    The semantic_score is preserved unchanged in the tuple; callers surface it
    separately from the decay-adjusted rank.
    """
    now = now or datetime.now(timezone.utc)
    scored = []
    for mem, sem_score in results:
        decay = compute_decay_factor(
            mem.memory_type,
            mem.created_at,
            mem.last_accessed_at,
            now,
        )
        scored.append((mem, sem_score, decay, sem_score * decay))
    scored.sort(key=lambda x: x[3], reverse=True)
    return [(mem, sem, decay) for mem, sem, decay, _ in scored]
