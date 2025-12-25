"""
Aegis ACE Repository

Database operations for ACE-enhanced features:
- Memory voting
- Delta updates
- Session progress
- Feature tracking
- Playbook queries
"""

import secrets
from datetime import datetime, timezone
from typing import Any

from embedding_service import content_hash
from models import (
    FeatureStatus,
    FeatureTracker,
    Memory,
    MemoryScope,
    MemoryType,
    SessionProgress,
    VoteHistory,
)
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


def generate_id() -> str:
    """Generate a short random ID."""
    return secrets.token_hex(16)


class ACERepository:
    """Repository for ACE-enhanced operations."""

    # ---------- Voting Operations ----------

    @staticmethod
    async def vote_memory(
        db: AsyncSession,
        memory_id: str,
        project_id: str,
        voter_agent_id: str,
        vote: str,
        context: str | None = None,
        task_id: str | None = None,
    ) -> Memory | None:
        """
        Record a vote on a memory and update counters.

        Returns the updated memory or None if not found.
        """
        # Get the memory
        result = await db.execute(
            select(Memory).where(
                and_(
                    Memory.id == memory_id,
                    Memory.project_id == project_id,
                )
            )
        )
        memory = result.scalar_one_or_none()

        if not memory:
            return None

        # Create vote history record
        vote_record = VoteHistory(
            id=generate_id(),
            memory_id=memory_id,
            project_id=project_id,
            voter_agent_id=voter_agent_id,
            vote=vote,
            context=context,
            task_id=task_id,
        )
        db.add(vote_record)

        # Update memory counters
        if vote == "helpful":
            memory.bullet_helpful += 1
        elif vote == "harmful":
            memory.bullet_harmful += 1

        memory.updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(memory)

        return memory

    @staticmethod
    async def get_vote_history(
        db: AsyncSession,
        memory_id: str,
        project_id: str,
        limit: int = 100,
    ) -> list[VoteHistory]:
        """Get vote history for a memory."""
        result = await db.execute(
            select(VoteHistory)
            .where(
                and_(
                    VoteHistory.memory_id == memory_id,
                    VoteHistory.project_id == project_id,
                )
            )
            .order_by(VoteHistory.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    # ---------- Delta Update Operations ----------

    @staticmethod
    async def update_memory_metadata(
        db: AsyncSession,
        memory_id: str,
        project_id: str,
        metadata_patch: dict[str, Any] | None = None,
    ) -> bool:
        """
        Update memory metadata with a patch.

        Returns True if memory was found and updated.
        """
        result = await db.execute(
            select(Memory).where(
                and_(
                    Memory.id == memory_id,
                    Memory.project_id == project_id,
                )
            )
        )
        memory = result.scalar_one_or_none()

        if not memory:
            return False

        if metadata_patch:
            current_metadata = memory.metadata_json or {}
            current_metadata.update(metadata_patch)
            memory.metadata_json = current_metadata

        memory.updated_at = datetime.now(timezone.utc)

        await db.commit()
        return True

    @staticmethod
    async def deprecate_memory(
        db: AsyncSession,
        memory_id: str,
        project_id: str,
        deprecated_by: str | None = None,
        superseded_by: str | None = None,
        reason: str | None = None,
    ) -> bool:
        """
        Soft-delete a memory by marking it deprecated.

        Preserves history while indicating the memory is outdated.
        Returns True if memory was found and deprecated.
        """
        result = await db.execute(
            select(Memory).where(
                and_(
                    Memory.id == memory_id,
                    Memory.project_id == project_id,
                )
            )
        )
        memory = result.scalar_one_or_none()

        if not memory:
            return False

        memory.is_deprecated = True
        memory.deprecated_at = datetime.now(timezone.utc)
        memory.deprecated_by = deprecated_by
        memory.superseded_by = superseded_by

        if reason:
            metadata = memory.metadata_json or {}
            metadata["deprecation_reason"] = reason
            memory.metadata_json = metadata

        memory.updated_at = datetime.now(timezone.utc)

        await db.commit()
        return True

    # ---------- Reflection Operations ----------

    @staticmethod
    async def create_reflection(
        db: AsyncSession,
        project_id: str,
        content: str,
        embedding: list[float],
        agent_id: str,
        user_id: str | None = None,
        namespace: str = "default",
        scope: str = MemoryScope.GLOBAL.value,
        metadata: dict[str, Any] | None = None,
        source_trajectory_id: str | None = None,
        error_pattern: str | None = None,
    ) -> Memory:
        """
        Create a reflection memory.

        Reflections are insights extracted from agent trajectories
        that help future tasks avoid mistakes.
        """
        now = datetime.now(timezone.utc)

        memory = Memory(
            id=generate_id(),
            project_id=project_id,
            content=content,
            content_hash=content_hash(content),
            embedding=embedding,
            user_id=user_id,
            agent_id=agent_id,
            namespace=namespace,
            scope=scope,
            memory_type=MemoryType.REFLECTION.value,
            metadata_json=metadata or {},
            source_trajectory_id=source_trajectory_id,
            error_pattern=error_pattern,
            created_at=now,
            updated_at=now,
        )

        db.add(memory)
        await db.commit()
        await db.refresh(memory)

        return memory

    # ---------- Playbook Query Operations ----------

    @staticmethod
    async def query_playbook(
        db: AsyncSession,
        query_embedding: list[float],
        project_id: str,
        namespace: str,
        requesting_agent_id: str,
        include_types: list[str],
        top_k: int = 20,
        min_effectiveness: float = -1.0,
    ) -> list[tuple[Memory, float]]:
        """
        Query playbook for relevant strategies and reflections.

        Results are filtered by:
        - Memory type (strategies, reflections)
        - Access control (scope)
        - Effectiveness score (helpful - harmful votes)
        - Not deprecated

        Ranked by semantic similarity.
        """
        from sqlalchemy import cast
        from sqlalchemy.dialects.postgresql import JSONB

        # Build access control filter using JSONB containment
        # Cast shared_with_agents to JSONB and check if it contains the agent ID
        shared_contains = cast(Memory.shared_with_agents, JSONB).contains(
            cast([requesting_agent_id], JSONB)
        )

        access_filter = or_(
            Memory.scope == MemoryScope.GLOBAL.value,
            Memory.agent_id == requesting_agent_id,
            shared_contains,
        )

        # Build base query with filters
        query = (
            select(
                Memory,
                (1 - Memory.embedding.cosine_distance(query_embedding)).label("score")
            )
            .where(
                and_(
                    Memory.project_id == project_id,
                    Memory.namespace == namespace,
                    Memory.memory_type.in_(include_types),
                    not Memory.is_deprecated,
                    access_filter,
                )
            )
            .order_by(Memory.embedding.cosine_distance(query_embedding))
            .limit(top_k * 2)  # Over-fetch for post-filtering
        )

        result = await db.execute(query)
        rows = result.all()

        # Post-filter by effectiveness score
        filtered = []
        for memory, score in rows:
            effectiveness = memory.get_effectiveness_score()
            if effectiveness >= min_effectiveness:
                filtered.append((memory, score))

        # Return top_k after filtering
        return filtered[:top_k]

    # ---------- Session Progress Operations ----------

    @staticmethod
    async def create_session(
        db: AsyncSession,
        project_id: str,
        session_id: str,
        agent_id: str | None = None,
        user_id: str | None = None,
        namespace: str = "default",
    ) -> SessionProgress:
        """Create a new session for progress tracking."""
        now = datetime.now(timezone.utc)

        session = SessionProgress(
            id=generate_id(),
            project_id=project_id,
            session_id=session_id,
            agent_id=agent_id,
            user_id=user_id,
            namespace=namespace,
            status="active",
            completed_items=[],
            next_items=[],
            blocked_items=[],
            created_at=now,
            updated_at=now,
        )

        db.add(session)
        await db.commit()
        await db.refresh(session)

        return session

    @staticmethod
    async def get_session(
        db: AsyncSession,
        session_id: str,
        project_id: str,
    ) -> SessionProgress | None:
        """Get session by session_id."""
        result = await db.execute(
            select(SessionProgress).where(
                and_(
                    SessionProgress.session_id == session_id,
                    SessionProgress.project_id == project_id,
                )
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_session(
        db: AsyncSession,
        session_id: str,
        project_id: str,
        completed_items: list[str] | None = None,
        in_progress_item: str | None = None,
        next_items: list[str] | None = None,
        blocked_items: list[dict] | None = None,
        summary: str | None = None,
        last_action: str | None = None,
        status: str | None = None,
        total_items: int | None = None,
    ) -> SessionProgress | None:
        """Update session progress."""
        result = await db.execute(
            select(SessionProgress).where(
                and_(
                    SessionProgress.session_id == session_id,
                    SessionProgress.project_id == project_id,
                )
            )
        )
        session = result.scalar_one_or_none()

        if not session:
            return None

        # Update fields if provided
        if completed_items is not None:
            # Merge with existing, avoiding duplicates
            existing = set(session.completed_items or [])
            existing.update(completed_items)
            session.completed_items = list(existing)
            session.completed_count = len(session.completed_items)

        if in_progress_item is not None:
            session.in_progress_item = in_progress_item

        if next_items is not None:
            session.next_items = next_items

        if blocked_items is not None:
            session.blocked_items = blocked_items

        if summary is not None:
            session.summary = summary

        if last_action is not None:
            session.last_action = last_action

        if status is not None:
            session.status = status

        if total_items is not None:
            session.total_items = total_items

        session.updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(session)

        return session

    # ---------- Feature Tracking Operations ----------

    @staticmethod
    async def create_feature(
        db: AsyncSession,
        project_id: str,
        feature_id: str,
        description: str,
        session_id: str | None = None,
        namespace: str = "default",
        category: str | None = None,
        test_steps: list[str] | None = None,
    ) -> FeatureTracker:
        """Create a feature to track."""
        now = datetime.now(timezone.utc)

        feature = FeatureTracker(
            id=generate_id(),
            project_id=project_id,
            session_id=session_id,
            namespace=namespace,
            feature_id=feature_id,
            category=category,
            description=description,
            test_steps=test_steps or [],
            status=FeatureStatus.NOT_STARTED.value,
            passes=False,
            created_at=now,
            updated_at=now,
        )

        db.add(feature)
        await db.commit()
        await db.refresh(feature)

        return feature

    @staticmethod
    async def get_feature(
        db: AsyncSession,
        feature_id: str,
        project_id: str,
        namespace: str = "default",
    ) -> FeatureTracker | None:
        """Get feature by feature_id."""
        result = await db.execute(
            select(FeatureTracker).where(
                and_(
                    FeatureTracker.feature_id == feature_id,
                    FeatureTracker.project_id == project_id,
                    FeatureTracker.namespace == namespace,
                )
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_feature(
        db: AsyncSession,
        feature_id: str,
        project_id: str,
        namespace: str = "default",
        status: str | None = None,
        passes: bool | None = None,
        implemented_by: str | None = None,
        verified_by: str | None = None,
        implementation_notes: str | None = None,
        failure_reason: str | None = None,
    ) -> FeatureTracker | None:
        """Update feature status."""
        result = await db.execute(
            select(FeatureTracker).where(
                and_(
                    FeatureTracker.feature_id == feature_id,
                    FeatureTracker.project_id == project_id,
                    FeatureTracker.namespace == namespace,
                )
            )
        )
        feature = result.scalar_one_or_none()

        if not feature:
            return None

        now = datetime.now(timezone.utc)

        if status is not None:
            feature.status = status

        if passes is not None:
            feature.passes = passes
            if passes:
                feature.completed_at = now

        if implemented_by is not None:
            feature.implemented_by = implemented_by

        if verified_by is not None:
            feature.verified_by = verified_by

        if implementation_notes is not None:
            feature.implementation_notes = implementation_notes

        if failure_reason is not None:
            feature.failure_reason = failure_reason

        feature.updated_at = now

        await db.commit()
        await db.refresh(feature)

        return feature

    @staticmethod
    async def list_features(
        db: AsyncSession,
        project_id: str,
        namespace: str = "default",
        session_id: str | None = None,
        status: str | None = None,
    ) -> list[FeatureTracker]:
        """List features with optional filters."""
        conditions = [
            FeatureTracker.project_id == project_id,
            FeatureTracker.namespace == namespace,
        ]

        if session_id:
            conditions.append(FeatureTracker.session_id == session_id)

        if status:
            conditions.append(FeatureTracker.status == status)

        result = await db.execute(
            select(FeatureTracker)
            .where(and_(*conditions))
            .order_by(FeatureTracker.created_at)
        )

        return list(result.scalars().all())
