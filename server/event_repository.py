"""Repository helpers for memory event timeline tracking."""

import secrets
from datetime import datetime, timezone
from typing import Any

from models import MemoryEvent
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession


class EventRepository:
    """Database operations for memory event timeline."""

    @staticmethod
    async def create_event(
        db: AsyncSession,
        *,
        memory_id: str | None,
        project_id: str,
        namespace: str,
        agent_id: str | None,
        event_type: str,
        event_payload: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> MemoryEvent:
        event = MemoryEvent(
            event_id=event_id or secrets.token_hex(16),
            memory_id=memory_id,
            project_id=project_id,
            namespace=namespace,
            agent_id=agent_id,
            event_type=event_type,
            event_payload=event_payload or {},
            created_at=datetime.now(timezone.utc),
        )
        db.add(event)
        await db.flush()
        return event

    @staticmethod
    async def get_project_timeline(
        db: AsyncSession,
        *,
        project_id: str,
        namespace: str | None = None,
        event_types: list[str] | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryEvent]:
        conditions = [MemoryEvent.project_id == project_id]

        if namespace:
            conditions.append(MemoryEvent.namespace == namespace)
        if event_types:
            conditions.append(MemoryEvent.event_type.in_(event_types))
        if start_time:
            conditions.append(MemoryEvent.created_at >= start_time)
        if end_time:
            conditions.append(MemoryEvent.created_at <= end_time)

        result = await db.execute(
            select(MemoryEvent)
            .where(and_(*conditions))
            .order_by(MemoryEvent.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_memory_timeline(
        db: AsyncSession,
        *,
        project_id: str,
        memory_id: str,
        event_types: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryEvent]:
        conditions = [
            MemoryEvent.project_id == project_id,
            MemoryEvent.memory_id == memory_id,
        ]

        if event_types:
            conditions.append(MemoryEvent.event_type.in_(event_types))

        result = await db.execute(
            select(MemoryEvent)
            .where(and_(*conditions))
            .order_by(MemoryEvent.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
