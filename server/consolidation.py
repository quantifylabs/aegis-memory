"""
Semantic Consolidation (v2.4.0).

Replaces the legacy first-50-char prefix match (server/ace_repository.py
~line 1024) with embedding-based pairwise consolidation.

Strategy:
  1. Find pairs with cosine similarity >= threshold (default 0.92 -- high bar).
  2. For each pair: heuristic (keep higher-effectiveness) OR LLM merge.
  3. Mark the "loser" deprecated; record consolidation in metadata.
  4. All actions go through dry_run=True by default -- caller explicitly applies.

This preserves audit trail: nothing is deleted; "loser" memories stay queryable
with is_deprecated=True and metadata.consolidated_into pointing at the keeper.
"""

from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import and_, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from event_repository import EventRepository
from models import Memory, MemoryEventType


class ConsolidationLLM(Protocol):
    async def merge(self, contents: list[str]) -> str:
        """Merge N similar memories into one canonical content."""
        ...


def _cosine_similarity(a, b) -> float:
    import numpy as np
    a_arr, b_arr = np.array(a, dtype=float), np.array(b, dtype=float)
    denom = (np.linalg.norm(a_arr) * np.linalg.norm(b_arr))
    if denom == 0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / denom)


class SemanticConsolidator:

    def __init__(
        self,
        similarity_threshold: float = 0.92,
        llm: ConsolidationLLM | None = None,
    ):
        self.similarity_threshold = similarity_threshold
        self.llm = llm

    async def find_pairs(
        self,
        db: AsyncSession,
        *,
        project_id: str,
        namespace: str = "default",
        agent_id: str | None = None,
        sample_limit: int = 500,
        max_pairs: int = 50,
    ) -> list[tuple[Memory, Memory, float]]:
        """
        Find candidate pairs. O(N^2) on the sampled set -- bounded by sample_limit.

        For larger corpuses, replace the inner loop with an HNSW-ANN pre-filter
        per anchor (each anchor searches its top-K neighbors and emits pairs
        above threshold). The interface stays the same.
        """
        conditions = [
            Memory.project_id == project_id,
            Memory.namespace == namespace,
            not_(Memory.is_deprecated),
            Memory.embedding.is_not(None),
        ]
        if agent_id:
            conditions.append(Memory.agent_id == agent_id)

        result = await db.execute(
            select(Memory).where(and_(*conditions))
            .order_by(Memory.created_at.desc())
            .limit(sample_limit)
        )
        memories = list(result.scalars().all())

        pairs: list[tuple[Memory, Memory, float]] = []
        for i, a in enumerate(memories):
            for b in memories[i + 1:]:
                sim = _cosine_similarity(a.embedding, b.embedding)
                if sim >= self.similarity_threshold:
                    pairs.append((a, b, sim))
            if len(pairs) >= max_pairs * 3:  # buffer for sort
                break

        pairs.sort(key=lambda p: p[2], reverse=True)
        return pairs[:max_pairs]

    async def consolidate_pair(
        self,
        db: AsyncSession,
        *,
        memory_a: Memory,
        memory_b: Memory,
        dry_run: bool = True,
    ) -> dict:
        """Merge a pair. Returns plan (and applies if dry_run=False)."""
        if self.llm is None:
            keeper, loser = (
                (memory_a, memory_b)
                if memory_a.get_effectiveness_score() >= memory_b.get_effectiveness_score()
                else (memory_b, memory_a)
            )
            merged_content = keeper.content
            strategy = "heuristic_keep_higher_effectiveness"
        else:
            merged_content = await self.llm.merge([memory_a.content, memory_b.content])
            keeper, loser = memory_a, memory_b
            strategy = "llm_merge"

        plan = {
            "keeper_id": keeper.id,
            "loser_id": loser.id,
            "merged_content_preview": merged_content[:200],
            "strategy": strategy,
            "applied": False,
        }

        if not dry_run:
            keeper.content = merged_content
            keeper_meta = dict(keeper.metadata_json or {})
            consolidated_from = list(keeper_meta.get("consolidated_from", []))
            consolidated_from.append(loser.id)
            keeper_meta["consolidated_from"] = consolidated_from
            keeper.metadata_json = keeper_meta

            loser.is_deprecated = True
            loser.deprecated_at = datetime.now(timezone.utc)
            loser.superseded_by = keeper.id
            loser_meta = dict(loser.metadata_json or {})
            loser_meta["consolidated_into"] = keeper.id
            loser.metadata_json = loser_meta

            await db.flush()

            await EventRepository.create_event(
                db, memory_id=keeper.id, project_id=keeper.project_id,
                namespace=keeper.namespace, agent_id=keeper.agent_id,
                event_type=MemoryEventType.MEMORIES_CONSOLIDATED.value,
                event_payload={
                    "keeper_id": keeper.id, "loser_id": loser.id,
                    "strategy": strategy,
                },
            )
            plan["applied"] = True

        return plan

    async def consolidate_batch(
        self,
        db: AsyncSession,
        *,
        project_id: str,
        namespace: str = "default",
        agent_id: str | None = None,
        dry_run: bool = True,
        max_pairs: int = 25,
    ) -> dict:
        pairs = await self.find_pairs(
            db, project_id=project_id, namespace=namespace,
            agent_id=agent_id, max_pairs=max_pairs,
        )
        plans = []
        for a, b, sim in pairs:
            # Re-check is_deprecated in case a previous iteration deactivated one
            if a.is_deprecated or b.is_deprecated:
                continue
            plan = await self.consolidate_pair(db, memory_a=a, memory_b=b, dry_run=dry_run)
            plan["similarity"] = sim
            plans.append(plan)
        return {
            "pairs_found": len(pairs),
            "pairs_processed": len(plans),
            "dry_run": dry_run,
            "plans": plans,
        }
