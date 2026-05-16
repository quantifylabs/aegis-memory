"""
Contradiction Detector (v2.4.0).

Two-stage strategy:
  Stage 1 (cheap): cosine similarity > threshold AND negation/opposition
                   marker present in either text. Runs in <10ms.
  Stage 2 (optional, opt-in): LLM pairwise confirmation. Adds ~1-2s/pair.

Default mode: stage 1 only. LLM stage activates if an LLM adapter is passed.

The cheap detector is intentionally high-recall, low-precision -- it surfaces
candidates for the human or LLM to confirm. False positives go through the
resolution workflow as "both_valid".
"""

import re
from typing import Protocol

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from event_repository import EventRepository
from memory_graph import EdgeType, MemoryGraphRepository
from models import Memory, MemoryEventType


NEGATION_PATTERNS = [
    r"\b(not|never|no|none|cannot|can't|won't|doesn't|don't|isn't|aren't|wasn't|weren't)\b",
    r"\b(false|wrong|incorrect|invalid|disabled|deprecated|removed|broken)\b",
    r"\b(unlike|opposite|contrary|contradicts|disagrees|conflicts)\b",
]
_NEG_RE = re.compile("|".join(NEGATION_PATTERNS), re.IGNORECASE)


class ContradictionLLM(Protocol):
    """Optional LLM adapter for stage-2 confirmation."""
    async def check(self, content_a: str, content_b: str) -> tuple[bool, float, str]:
        """Returns (is_contradiction, confidence_0_to_1, rationale)."""
        ...


class ContradictionDetector:

    def __init__(
        self,
        similarity_threshold: float = 0.80,
        llm: ContradictionLLM | None = None,
    ):
        self.similarity_threshold = similarity_threshold
        self.llm = llm

    @staticmethod
    def has_opposition_signal(content_a: str, content_b: str) -> bool:
        return bool(_NEG_RE.search(content_a) or _NEG_RE.search(content_b))

    async def scan_memory(
        self,
        db: AsyncSession,
        *,
        memory: Memory,
        top_neighbors: int = 5,
    ) -> list[tuple[Memory, float, str]]:
        """Find candidate contradictions for a single memory."""
        if memory.embedding is None:
            return []

        distance = Memory.embedding.cosine_distance(memory.embedding)
        result = await db.execute(
            select(Memory, distance.label("d"))
            .where(and_(
                Memory.project_id == memory.project_id,
                Memory.namespace == memory.namespace,
                Memory.id != memory.id,
                Memory.embedding.is_not(None),
            ))
            .order_by(distance)
            .limit(top_neighbors + 1)  # +1 because self may slip in
        )

        candidates: list[tuple[Memory, float, str]] = []
        for cand, dist in result.all():
            if cand.id == memory.id:
                continue
            similarity = 1.0 - float(dist)
            if similarity < self.similarity_threshold:
                break  # ordered ascending by distance -- once below threshold, stop
            if not self.has_opposition_signal(memory.content, cand.content):
                continue

            if self.llm is None:
                candidates.append((cand, similarity, "cheap:high_sim+opposition_marker"))
            else:
                is_contra, conf, rationale = await self.llm.check(
                    memory.content, cand.content
                )
                if is_contra:
                    candidates.append((cand, conf, f"llm:{rationale}"))

        return candidates

    async def detect_and_record(
        self,
        db: AsyncSession,
        *,
        memory: Memory,
        top_neighbors: int = 5,
    ) -> list[str]:
        """Detect contradictions and write edges. Returns new edge IDs."""
        candidates = await self.scan_memory(
            db, memory=memory, top_neighbors=top_neighbors,
        )
        edge_ids: list[str] = []
        for cand, confidence, rationale in candidates:
            edge = await MemoryGraphRepository.add_edge(
                db,
                project_id=memory.project_id,
                source_id=memory.id,
                target_id=cand.id,
                edge_type=EdgeType.CONTRADICTS.value,
                confidence=confidence,
                detected_by=("llm" if self.llm else "cheap") + "_detector_v2.4.0",
                metadata={"rationale": rationale},
            )
            edge_ids.append(edge.id)
            await EventRepository.create_event(
                db,
                memory_id=memory.id,
                project_id=memory.project_id,
                namespace=memory.namespace,
                agent_id=memory.agent_id,
                event_type=MemoryEventType.CONTRADICTION_DETECTED.value,
                event_payload={
                    "edge_id": edge.id,
                    "other_memory_id": cand.id,
                    "confidence": confidence,
                    "rationale": rationale,
                },
            )
        return edge_ids
