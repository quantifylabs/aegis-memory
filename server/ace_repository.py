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
from event_repository import EventRepository
from observability import OperationNames, record_operation, track_latency
from models import (
    AceRun,
    FeatureStatus,
    FeatureTracker,
    Memory,
    MemoryScope,
    MemorySharedAgent,
    MemoryType,
    SessionProgress,
    VoteHistory,
    MemoryEventType,
)
from sqlalchemy import and_, not_, or_, select, update
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

        Uses atomic SQL increment to prevent race conditions from
        concurrent votes losing updates.

        Returns the updated memory or None if not found.
        """
        try:
            with track_latency(OperationNames.MEMORY_VOTE):
                result = await db.execute(
                    select(Memory.id).where(
                        and_(
                            Memory.id == memory_id,
                            Memory.project_id == project_id,
                        )
                    )
                )
                if result.scalar_one_or_none() is None:
                    record_operation(OperationNames.MEMORY_VOTE, "error")
                    return None

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

                now = datetime.now(timezone.utc)
                if vote == "helpful":
                    stmt = (
                        update(Memory)
                        .where(and_(Memory.id == memory_id, Memory.project_id == project_id))
                        .values(bullet_helpful=Memory.bullet_helpful + 1, updated_at=now)
                        .returning(Memory.id)
                    )
                    await db.execute(stmt)
                elif vote == "harmful":
                    stmt = (
                        update(Memory)
                        .where(and_(Memory.id == memory_id, Memory.project_id == project_id))
                        .values(bullet_harmful=Memory.bullet_harmful + 1, updated_at=now)
                        .returning(Memory.id)
                    )
                    await db.execute(stmt)

                await db.flush()

                result = await db.execute(select(Memory).where(Memory.id == memory_id))
                memory = result.scalar_one_or_none()

                if memory is not None:
                    await EventRepository.create_event(
                        db,
                        memory_id=memory_id,
                        project_id=project_id,
                        namespace=memory.namespace,
                        agent_id=voter_agent_id,
                        event_type=(
                            MemoryEventType.VOTED_HELPFUL.value
                            if vote == "helpful"
                            else MemoryEventType.VOTED_HARMFUL.value
                        ),
                        event_payload={"task_id": task_id, "context": context},
                    )

            record_operation(OperationNames.MEMORY_VOTE, "success")
            return memory
        except Exception:
            record_operation(OperationNames.MEMORY_VOTE, "error")
            raise

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

        await EventRepository.create_event(
            db,
            memory_id=memory.id,
            project_id=project_id,
            namespace=memory.namespace,
            agent_id=memory.agent_id,
            event_type=MemoryEventType.DELTA_UPDATED.value,
            event_payload={"metadata_patch": metadata_patch or {}},
        )

        with track_latency(OperationNames.MEMORY_DELTA_UPDATE):
            await db.flush()
        record_operation(OperationNames.MEMORY_DELTA_UPDATE, "success")
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

        await EventRepository.create_event(
            db,
            memory_id=memory.id,
            project_id=project_id,
            namespace=memory.namespace,
            agent_id=deprecated_by or memory.agent_id,
            event_type=MemoryEventType.DEPRECATED.value,
            event_payload={"superseded_by": superseded_by, "reason": reason},
        )

        with track_latency(OperationNames.MEMORY_DELTA_DEPRECATE):
            await db.flush()
        record_operation(OperationNames.MEMORY_DELTA_DEPRECATE, "success")
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

        with track_latency(OperationNames.MEMORY_REFLECTION):
            db.add(memory)
            await EventRepository.create_event(
                db,
                memory_id=memory.id,
                project_id=project_id,
                namespace=namespace,
                agent_id=agent_id,
                event_type=MemoryEventType.REFLECTED.value,
                event_payload={"source_trajectory_id": source_trajectory_id, "error_pattern": error_pattern},
            )
            await db.flush()
            await db.refresh(memory)

        record_operation(OperationNames.MEMORY_REFLECTION, "success")
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
        # Build access control filter using normalized join table
        shared_subquery = (
            select(MemorySharedAgent.memory_id)
            .where(MemorySharedAgent.shared_agent_id == requesting_agent_id)
        )

        access_filter = or_(
            Memory.scope == MemoryScope.GLOBAL.value,
            Memory.agent_id == requesting_agent_id,
            Memory.id.in_(shared_subquery),
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
                    not_(Memory.is_deprecated),
                    access_filter,
                )
            )
            .order_by(Memory.embedding.cosine_distance(query_embedding))
            .limit(top_k * 2)  # Over-fetch for post-filtering
        )

        with track_latency(OperationNames.MEMORY_QUERY):
            result = await db.execute(query)
            rows = result.all()
        record_operation(OperationNames.MEMORY_QUERY, "success")

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

        with track_latency(OperationNames.MEMORY_SESSION_CREATE):
            db.add(session)
            await EventRepository.create_event(
                db,
                memory_id=None,
                project_id=project_id,
                namespace=namespace,
                agent_id=agent_id,
                event_type=MemoryEventType.CREATED.value,
                event_payload={"source": "session", "session_id": session_id},
            )
            await db.flush()
            await db.refresh(session)

        record_operation(OperationNames.MEMORY_SESSION_CREATE, "success")
        return session

    @staticmethod
    async def get_session(
        db: AsyncSession,
        session_id: str,
        project_id: str,
    ) -> SessionProgress | None:
        """Get session by session_id."""
        with track_latency(OperationNames.MEMORY_SESSION_GET):
            result = await db.execute(
                select(SessionProgress).where(
                    and_(
                        SessionProgress.session_id == session_id,
                        SessionProgress.project_id == project_id,
                    )
                )
            )
        record_operation(OperationNames.MEMORY_SESSION_GET, "success")
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

        await EventRepository.create_event(
            db,
            memory_id=None,
            project_id=project_id,
            namespace=session.namespace,
            agent_id=session.agent_id,
            event_type=MemoryEventType.DELTA_UPDATED.value,
            event_payload={"source": "session", "session_id": session_id, "status": session.status},
        )

        with track_latency(OperationNames.MEMORY_SESSION_UPDATE):
            await db.flush()
            await db.refresh(session)

        record_operation(OperationNames.MEMORY_SESSION_UPDATE, "success")
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

        with track_latency(OperationNames.MEMORY_FEATURE_CREATE):
            db.add(feature)
            await EventRepository.create_event(
                db,
                memory_id=None,
                project_id=project_id,
                namespace=namespace,
                agent_id=None,
                event_type=MemoryEventType.CREATED.value,
                event_payload={"source": "feature", "feature_id": feature_id, "status": FeatureStatus.NOT_STARTED.value},
            )
            await db.flush()
            await db.refresh(feature)

        record_operation(OperationNames.MEMORY_FEATURE_CREATE, "success")
        return feature

    @staticmethod
    async def get_feature(
        db: AsyncSession,
        feature_id: str,
        project_id: str,
        namespace: str = "default",
    ) -> FeatureTracker | None:
        """Get feature by feature_id."""
        with track_latency(OperationNames.MEMORY_FEATURE_GET):
            result = await db.execute(
                select(FeatureTracker).where(
                    and_(
                        FeatureTracker.feature_id == feature_id,
                        FeatureTracker.project_id == project_id,
                        FeatureTracker.namespace == namespace,
                    )
                )
            )
        record_operation(OperationNames.MEMORY_FEATURE_GET, "success")
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
        task_id: str | None = None,
        retrieval_event_id: str | None = None,
        selected_memory_ids: list[str] | None = None,
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

        await EventRepository.create_event(
            db,
            memory_id=None,
            project_id=project_id,
            namespace=namespace,
            agent_id=implemented_by or verified_by,
            event_type=MemoryEventType.DELTA_UPDATED.value,
            event_payload={"source": "feature", "feature_id": feature_id, "status": feature.status, "passes": feature.passes},
            task_id=task_id or feature_id,
            retrieval_event_id=retrieval_event_id,
            selected_memory_ids=selected_memory_ids or [],
        )

        with track_latency(OperationNames.MEMORY_FEATURE_UPDATE):
            await db.flush()
            await db.refresh(feature)

        record_operation(OperationNames.MEMORY_FEATURE_UPDATE, "success")
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

        with track_latency(OperationNames.MEMORY_FEATURE_LIST):
            result = await db.execute(
                select(FeatureTracker)
                .where(and_(*conditions))
                .order_by(FeatureTracker.created_at)
            )

        record_operation(OperationNames.MEMORY_FEATURE_LIST, "success")
        return list(result.scalars().all())

    # ---------- ACE Run Tracking Operations ----------

    @staticmethod
    async def create_run(
        db: AsyncSession,
        project_id: str,
        run_id: str,
        agent_id: str | None = None,
        task_type: str | None = None,
        namespace: str = "default",
        memory_ids_used: list[str] | None = None,
    ) -> AceRun:
        """Create a new ACE run with status='running'."""
        now = datetime.now(timezone.utc)

        run = AceRun(
            id=generate_id(),
            project_id=project_id,
            run_id=run_id,
            agent_id=agent_id,
            task_type=task_type,
            namespace=namespace,
            status="running",
            memory_ids_used=memory_ids_used or [],
            reflection_ids=[],
            evaluation={},
            logs={},
            started_at=now,
            created_at=now,
            updated_at=now,
        )

        with track_latency(OperationNames.MEMORY_RUN_CREATE):
            db.add(run)
            await EventRepository.create_event(
                db,
                memory_id=None,
                project_id=project_id,
                namespace=namespace,
                agent_id=agent_id,
                event_type=MemoryEventType.RUN_STARTED.value,
                event_payload={"run_id": run_id, "task_type": task_type},
            )
            await db.flush()
            await db.refresh(run)

        record_operation(OperationNames.MEMORY_RUN_CREATE, "success")
        return run

    @staticmethod
    async def get_run(
        db: AsyncSession,
        run_id: str,
        project_id: str,
    ) -> AceRun | None:
        """Get run by run_id."""
        with track_latency(OperationNames.MEMORY_RUN_GET):
            result = await db.execute(
                select(AceRun).where(
                    and_(
                        AceRun.run_id == run_id,
                        AceRun.project_id == project_id,
                    )
                )
            )
        record_operation(OperationNames.MEMORY_RUN_GET, "success")
        return result.scalar_one_or_none()

    @staticmethod
    async def complete_run(
        db: AsyncSession,
        run_id: str,
        project_id: str,
        success: bool,
        evaluation: dict[str, Any] | None = None,
        logs: dict[str, Any] | None = None,
        auto_vote: bool = True,
        auto_reflect: bool = True,
        embed_fn: Any | None = None,
    ) -> AceRun | None:
        """
        Complete an ACE run with feedback.

        - Auto-vote: iterate memory_ids_used, vote 'helpful' if success, 'harmful' if failed
        - Auto-reflect: if failed and evaluation includes error info, create a reflection memory
        - Emit RUN_COMPLETED event
        """
        result = await db.execute(
            select(AceRun).where(
                and_(
                    AceRun.run_id == run_id,
                    AceRun.project_id == project_id,
                )
            )
        )
        run = result.scalar_one_or_none()

        if not run:
            return None

        now = datetime.now(timezone.utc)
        run.status = "completed" if success else "failed"
        run.success = success
        run.evaluation = evaluation or {}
        run.logs = logs or {}
        run.completed_at = now
        run.updated_at = now

        # Auto-vote on memories used
        if auto_vote and run.memory_ids_used:
            vote_type = "helpful" if success else "harmful"
            voter = run.agent_id or "ace-loop"
            for memory_id in run.memory_ids_used:
                await ACERepository.vote_memory(
                    db,
                    memory_id=memory_id,
                    project_id=project_id,
                    voter_agent_id=voter,
                    vote=vote_type,
                    context=f"Auto-vote from run {run_id} (success={success})",
                    task_id=run_id,
                )

        # Auto-reflect on failure
        reflection_ids = []
        if auto_reflect and not success and embed_fn is not None:
            error_info = (evaluation or {}).get("error", "")
            error_pattern = (evaluation or {}).get("error_pattern", "run_failure")
            if error_info:
                reflection_content = (
                    f"Run '{run_id}' failed. Error: {error_info}. "
                    f"Task type: {run.task_type or 'unknown'}. "
                    f"Memories used: {len(run.memory_ids_used)}."
                )
                embedding = await embed_fn(reflection_content)
                reflection = await ACERepository.create_reflection(
                    db,
                    project_id=project_id,
                    content=reflection_content,
                    embedding=embedding,
                    agent_id=run.agent_id or "ace-loop",
                    namespace=run.namespace,
                    source_trajectory_id=run_id,
                    error_pattern=error_pattern,
                    metadata={"auto_generated": True, "run_id": run_id},
                )
                reflection_ids.append(reflection.id)

        run.reflection_ids = reflection_ids

        await EventRepository.create_event(
            db,
            memory_id=None,
            project_id=project_id,
            namespace=run.namespace,
            agent_id=run.agent_id,
            event_type=MemoryEventType.RUN_COMPLETED.value,
            event_payload={
                "run_id": run_id,
                "success": success,
                "auto_vote": auto_vote,
                "auto_reflect": auto_reflect,
                "reflection_ids": reflection_ids,
                "memories_voted": len(run.memory_ids_used) if auto_vote else 0,
            },
        )

        with track_latency(OperationNames.MEMORY_RUN_COMPLETE):
            await db.flush()
            await db.refresh(run)

        record_operation(OperationNames.MEMORY_RUN_COMPLETE, "success")
        return run

    @staticmethod
    async def get_playbook_for_agent(
        db: AsyncSession,
        query_embedding: list[float],
        project_id: str,
        agent_id: str,
        namespace: str = "default",
        task_type: str | None = None,
        top_k: int = 20,
        min_effectiveness: float = -1.0,
    ) -> list[tuple[Memory, float]]:
        """
        Query playbook filtered by agent_id + optional task_type.

        Boosts entries validated by successful runs by sorting with
        linked run count + effectiveness.
        """
        # Build access control filter
        shared_subquery = (
            select(MemorySharedAgent.memory_id)
            .where(MemorySharedAgent.shared_agent_id == agent_id)
        )

        access_filter = or_(
            Memory.scope == MemoryScope.GLOBAL.value,
            Memory.agent_id == agent_id,
            Memory.id.in_(shared_subquery),
        )

        include_types = [MemoryType.STRATEGY.value, MemoryType.REFLECTION.value]

        # Build base query
        conditions = [
            Memory.project_id == project_id,
            Memory.namespace == namespace,
            Memory.memory_type.in_(include_types),
            not_(Memory.is_deprecated),
            access_filter,
        ]

        # Filter by agent_id: include global entries + agent-specific entries
        conditions.append(
            or_(
                Memory.agent_id == agent_id,
                Memory.scope == MemoryScope.GLOBAL.value,
                Memory.agent_id.is_(None),
            )
        )

        query = (
            select(
                Memory,
                (1 - Memory.embedding.cosine_distance(query_embedding)).label("score")
            )
            .where(and_(*conditions))
            .order_by(Memory.embedding.cosine_distance(query_embedding))
            .limit(top_k * 2)
        )

        with track_latency(OperationNames.MEMORY_PLAYBOOK_AGENT):
            result = await db.execute(query)
            rows = result.all()
        record_operation(OperationNames.MEMORY_PLAYBOOK_AGENT, "success")

        # Post-filter by effectiveness and optional task_type metadata
        filtered = []
        for memory, score in rows:
            effectiveness = memory.get_effectiveness_score()
            if effectiveness < min_effectiveness:
                continue
            # If task_type specified, prefer entries with matching task_type in metadata
            if task_type:
                meta = memory.metadata_json or {}
                entry_task_type = meta.get("task_type")
                if entry_task_type and entry_task_type != task_type:
                    continue
            filtered.append((memory, score))

        return filtered[:top_k]

    @staticmethod
    async def curate(
        db: AsyncSession,
        project_id: str,
        namespace: str = "default",
        agent_id: str | None = None,
        top_k: int = 10,
        min_effectiveness_threshold: float = -0.3,
    ) -> dict[str, Any]:
        """
        Curation cycle: identify effective, flag ineffective, suggest consolidations.

        Returns a dict with:
        - promoted: list of high-effectiveness memory summaries
        - flagged: list of low-effectiveness memory summaries
        - consolidation_candidates: list of pairs of similar memories
        """
        conditions = [
            Memory.project_id == project_id,
            Memory.namespace == namespace,
            Memory.memory_type.in_([MemoryType.STRATEGY.value, MemoryType.REFLECTION.value]),
            not_(Memory.is_deprecated),
        ]

        if agent_id:
            conditions.append(
                or_(
                    Memory.agent_id == agent_id,
                    Memory.scope == MemoryScope.GLOBAL.value,
                )
            )

        with track_latency(OperationNames.MEMORY_CURATE):
            result = await db.execute(
                select(Memory)
                .where(and_(*conditions))
                .order_by(Memory.created_at)
            )
            all_memories = list(result.scalars().all())

        # Score all memories
        scored = []
        for mem in all_memories:
            effectiveness = mem.get_effectiveness_score()
            total_votes = mem.bullet_helpful + mem.bullet_harmful
            scored.append({
                "id": mem.id,
                "content": mem.content[:200],
                "memory_type": mem.memory_type,
                "effectiveness_score": effectiveness,
                "bullet_helpful": mem.bullet_helpful,
                "bullet_harmful": mem.bullet_harmful,
                "total_votes": total_votes,
            })

        # Sort by effectiveness
        scored.sort(key=lambda x: x["effectiveness_score"], reverse=True)

        # Promoted: top-k effective (with positive scores and votes)
        promoted = [s for s in scored if s["effectiveness_score"] > 0 and s["total_votes"] > 0][:top_k]

        # Flagged: bottom entries below threshold
        flagged = [s for s in scored if s["effectiveness_score"] < min_effectiveness_threshold and s["total_votes"] > 0][:top_k]

        # Consolidation candidates: find memories with similar content (simple length + prefix check)
        consolidation_candidates = []
        for i in range(len(all_memories)):
            for j in range(i + 1, len(all_memories)):
                a, b = all_memories[i], all_memories[j]
                # Simple heuristic: same type, same first 50 chars (normalized)
                if a.memory_type == b.memory_type:
                    a_prefix = a.content[:50].lower().strip()
                    b_prefix = b.content[:50].lower().strip()
                    if a_prefix == b_prefix and a.id != b.id:
                        consolidation_candidates.append({
                            "memory_id_a": a.id,
                            "memory_id_b": b.id,
                            "content_a": a.content[:100],
                            "content_b": b.content[:100],
                            "reason": "similar_content_prefix",
                        })

        await EventRepository.create_event(
            db,
            memory_id=None,
            project_id=project_id,
            namespace=namespace,
            agent_id=agent_id,
            event_type=MemoryEventType.CURATED.value,
            event_payload={
                "promoted_count": len(promoted),
                "flagged_count": len(flagged),
                "consolidation_count": len(consolidation_candidates),
                "total_evaluated": len(scored),
            },
        )

        record_operation(OperationNames.MEMORY_CURATE, "success")
        return {
            "promoted": promoted,
            "flagged": flagged,
            "consolidation_candidates": consolidation_candidates,
        }
