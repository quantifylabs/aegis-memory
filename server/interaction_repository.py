"""Repository helpers for interaction event tracking."""

import secrets
from datetime import datetime, timezone
from typing import Any

from event_repository import EventRepository
from models import InteractionEvent, MemoryEventType
from observability import OperationNames, record_operation, track_latency
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession


class InteractionRepository:
    """Database operations for interaction event timeline."""

    @staticmethod
    async def create_event(
        db: AsyncSession,
        *,
        project_id: str,
        session_id: str,
        content: str,
        agent_id: str | None = None,
        tool_calls: list | None = None,
        parent_event_id: str | None = None,
        namespace: str = "default",
        extra_metadata: dict[str, Any] | None = None,
        embedding: list | None = None,
    ) -> InteractionEvent:
        """Insert an interaction event and emit a timeline event."""
        with track_latency(OperationNames.INTERACTION_CREATE):
            event = InteractionEvent(
                event_id=secrets.token_hex(16),
                project_id=project_id,
                session_id=session_id,
                agent_id=agent_id,
                content=content,
                timestamp=datetime.now(timezone.utc),
                tool_calls=tool_calls or [],
                parent_event_id=parent_event_id,
                namespace=namespace,
                extra_metadata=extra_metadata,
                embedding=embedding,
            )
            db.add(event)
            await EventRepository.create_event(
                db,
                memory_id=None,
                project_id=project_id,
                namespace=namespace,
                agent_id=agent_id,
                event_type=MemoryEventType.INTERACTION_CREATED.value,
                event_payload={"session_id": session_id, "event_id": event.event_id},
            )
            await db.flush()
            record_operation(OperationNames.INTERACTION_CREATE, "success")
        return event

    @staticmethod
    async def get_event(
        db: AsyncSession,
        *,
        event_id: str,
        project_id: str,
    ) -> InteractionEvent | None:
        """Single lookup by primary key, scoped to project."""
        with track_latency(OperationNames.INTERACTION_GET):
            result = await db.execute(
                select(InteractionEvent).where(
                    and_(
                        InteractionEvent.event_id == event_id,
                        InteractionEvent.project_id == project_id,
                    )
                )
            )
            event = result.scalar_one_or_none()
            record_operation(OperationNames.INTERACTION_GET, "success")
        return event

    @staticmethod
    async def get_session_timeline(
        db: AsyncSession,
        *,
        project_id: str,
        session_id: str,
        namespace: str = "default",
        limit: int = 100,
        offset: int = 0,
    ) -> list[InteractionEvent]:
        """
        Fetch all events for a session ordered by timestamp ASC.

        Uses ix_interaction_project_session_ts composite index.
        """
        with track_latency(OperationNames.INTERACTION_SESSION_TIMELINE):
            conditions = [
                InteractionEvent.project_id == project_id,
                InteractionEvent.session_id == session_id,
                InteractionEvent.namespace == namespace,
            ]
            result = await db.execute(
                select(InteractionEvent)
                .where(and_(*conditions))
                .order_by(InteractionEvent.timestamp.asc())
                .limit(limit)
                .offset(offset)
            )
            events = list(result.scalars().all())
            record_operation(OperationNames.INTERACTION_SESSION_TIMELINE, "success")
        return events

    @staticmethod
    async def get_agent_interactions(
        db: AsyncSession,
        *,
        project_id: str,
        agent_id: str,
        namespace: str = "default",
        limit: int = 100,
        offset: int = 0,
    ) -> list[InteractionEvent]:
        """
        Fetch all events for an agent ordered by timestamp DESC (most recent first).

        Uses ix_interaction_project_agent_ts composite index.
        """
        with track_latency(OperationNames.INTERACTION_AGENT_HISTORY):
            conditions = [
                InteractionEvent.project_id == project_id,
                InteractionEvent.agent_id == agent_id,
                InteractionEvent.namespace == namespace,
            ]
            result = await db.execute(
                select(InteractionEvent)
                .where(and_(*conditions))
                .order_by(InteractionEvent.timestamp.desc())
                .limit(limit)
                .offset(offset)
            )
            events = list(result.scalars().all())
            record_operation(OperationNames.INTERACTION_AGENT_HISTORY, "success")
        return events

    @staticmethod
    async def search(
        db: AsyncSession,
        *,
        project_id: str,
        query_embedding: list,
        namespace: str = "default",
        session_id: str | None = None,
        agent_id: str | None = None,
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[tuple[InteractionEvent, float]]:
        """
        Cosine similarity search over interaction events.

        Only considers events where embedding IS NOT NULL.
        Returns list of (event, score) tuples ordered by similarity DESC.
        """
        with track_latency(OperationNames.INTERACTION_SEARCH):
            from sqlalchemy import text as sa_text

            conditions = [
                InteractionEvent.project_id == project_id,
                InteractionEvent.namespace == namespace,
                InteractionEvent.embedding.isnot(None),
            ]
            if session_id:
                conditions.append(InteractionEvent.session_id == session_id)
            if agent_id:
                conditions.append(InteractionEvent.agent_id == agent_id)

            distance_col = InteractionEvent.embedding.cosine_distance(query_embedding)
            result = await db.execute(
                select(InteractionEvent, distance_col.label("distance"))
                .where(and_(*conditions))
                .order_by(distance_col.asc())
                .limit(top_k)
            )
            rows = result.all()

            # Convert distance to similarity score (cosine similarity = 1 - distance)
            scored = [
                (row[0], round(1.0 - row[1], 6))
                for row in rows
                if (1.0 - row[1]) >= min_score
            ]
            record_operation(OperationNames.INTERACTION_SEARCH, "success")
        return scored

    @staticmethod
    async def get_with_chain(
        db: AsyncSession,
        *,
        event_id: str,
        project_id: str,
        max_depth: int = 10,
    ) -> list[InteractionEvent]:
        """
        Walk the causal chain from event_id up to the root.

        Returns events ordered root → leaf. Includes cycle guard via
        a seen set to handle any unexpected circular references.
        """
        with track_latency(OperationNames.INTERACTION_CHAIN):
            chain: list[InteractionEvent] = []
            seen: set[str] = set()
            current_id: str | None = event_id

            for _ in range(max_depth):
                if current_id is None or current_id in seen:
                    break
                seen.add(current_id)

                result = await db.execute(
                    select(InteractionEvent).where(
                        and_(
                            InteractionEvent.event_id == current_id,
                            InteractionEvent.project_id == project_id,
                        )
                    )
                )
                event = result.scalar_one_or_none()
                if event is None:
                    break

                chain.append(event)
                current_id = event.parent_event_id

            record_operation(OperationNames.INTERACTION_CHAIN, "success")

        # chain is built leaf → root; reverse to get root → leaf
        return list(reversed(chain))
