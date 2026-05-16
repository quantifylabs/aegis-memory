"""Memory Graph (v2.4.0) -- typed edges between memories."""

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import MemoryEdge


class EdgeType(str, Enum):
    SUPERSEDES = "supersedes"
    CONTRADICTS = "contradicts"
    GENERALIZES = "generalizes"
    ELABORATES = "elaborates"
    DERIVES_FROM = "derives_from"
    ENTITY_REL = "entity_rel"


class EdgeResolution(str, Enum):
    UNRESOLVED = "unresolved"
    KEPT_SOURCE = "kept_source"
    KEPT_TARGET = "kept_target"
    BOTH_VALID = "both_valid"
    BOTH_INVALID = "both_invalid"


class MemoryGraphRepository:

    @staticmethod
    async def add_edge(
        db: AsyncSession,
        *,
        project_id: str,
        source_id: str,
        target_id: str,
        edge_type: str,
        confidence: float = 1.0,
        detected_by: str = "manual",
        metadata: dict | None = None,
    ) -> MemoryEdge:
        # Idempotency: the (source, target, type) unique index prevents duplicates.
        # Use ON CONFLICT DO NOTHING semantics by selecting first.
        result = await db.execute(
            select(MemoryEdge).where(and_(
                MemoryEdge.source_memory_id == source_id,
                MemoryEdge.target_memory_id == target_id,
                MemoryEdge.edge_type == edge_type,
            ))
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

        edge = MemoryEdge(
            id=uuid4().hex,
            project_id=project_id,
            source_memory_id=source_id,
            target_memory_id=target_id,
            edge_type=edge_type,
            confidence=confidence,
            detected_by=detected_by,
            metadata_json=metadata or {},
            resolution=EdgeResolution.UNRESOLVED.value,
        )
        db.add(edge)
        await db.flush()
        return edge

    @staticmethod
    async def get_edges_for_memory(
        db: AsyncSession,
        memory_id: str,
        project_id: str,
        edge_type: str | None = None,
        include_resolved: bool = False,
    ) -> list[MemoryEdge]:
        conditions = [
            MemoryEdge.project_id == project_id,
            or_(
                MemoryEdge.source_memory_id == memory_id,
                MemoryEdge.target_memory_id == memory_id,
            ),
        ]
        if edge_type:
            conditions.append(MemoryEdge.edge_type == edge_type)
        if not include_resolved:
            conditions.append(MemoryEdge.resolution == EdgeResolution.UNRESOLVED.value)

        result = await db.execute(
            select(MemoryEdge).where(and_(*conditions))
            .order_by(MemoryEdge.confidence.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_unresolved_contradictions(
        db: AsyncSession,
        project_id: str,
        limit: int = 100,
    ) -> list[MemoryEdge]:
        result = await db.execute(
            select(MemoryEdge).where(and_(
                MemoryEdge.project_id == project_id,
                MemoryEdge.edge_type == EdgeType.CONTRADICTS.value,
                MemoryEdge.resolution == EdgeResolution.UNRESOLVED.value,
            )).order_by(MemoryEdge.detected_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def resolve(
        db: AsyncSession,
        edge_id: str,
        resolution: str,
        resolved_by: str | None = None,
    ) -> MemoryEdge | None:
        if resolution not in {r.value for r in EdgeResolution}:
            raise ValueError(f"invalid resolution: {resolution}")
        result = await db.execute(select(MemoryEdge).where(MemoryEdge.id == edge_id))
        edge = result.scalar_one_or_none()
        if edge is None:
            return None
        edge.resolution = resolution
        edge.resolved_by = resolved_by
        edge.resolved_at = datetime.now(timezone.utc)
        await db.flush()
        return edge

    @staticmethod
    async def contradiction_metrics(
        db: AsyncSession,
        project_id: str,
    ) -> dict:
        """For Simulation Reliability Index -- count active contradictions."""
        unresolved = await db.execute(
            select(func.count(MemoryEdge.id)).where(and_(
                MemoryEdge.project_id == project_id,
                MemoryEdge.edge_type == EdgeType.CONTRADICTS.value,
                MemoryEdge.resolution == EdgeResolution.UNRESOLVED.value,
            ))
        )
        total = await db.execute(
            select(func.count(MemoryEdge.id)).where(and_(
                MemoryEdge.project_id == project_id,
                MemoryEdge.edge_type == EdgeType.CONTRADICTS.value,
            ))
        )
        return {
            "unresolved_contradictions": unresolved.scalar() or 0,
            "total_contradictions_detected": total.scalar() or 0,
        }
