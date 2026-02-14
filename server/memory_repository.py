"""
Aegis Production Memory Repository

This is where the real scalability magic happens:
- Uses pgvector's native similarity search (HNSW index)
- Pre-filters BEFORE vector search (critical for performance)
- Proper query planning for multi-tenant workloads

ACE Enhancements:
- Memory type filtering
- Deprecated memory exclusion
- Effectiveness score support
"""

import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from embedding_service import content_hash
from models import Memory, MemoryScope, MemorySharedAgent, MemoryType
from observability import OperationNames, record_operation, record_query_execution, track_latency
from sqlalchemy import and_, cast, delete, exists, not_, or_, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession


class MemoryRepository:
    """
    Production memory repository with O(log n) vector search.

    Query Strategy:
    1. Build filter predicates (project_id, namespace, scope, etc.)
    2. Use pgvector's <=> operator with HNSW index
    3. Let PostgreSQL's query planner optimize the join

    The key insight: pgvector can apply filters BEFORE the ANN search
    when using the right query structure.
    """

    @staticmethod
    async def add(
        db: AsyncSession,
        *,
        project_id: str,
        content: str,
        embedding: list[float],
        user_id: str | None = None,
        agent_id: str | None = None,
        namespace: str = "default",
        metadata: dict | None = None,
        ttl_seconds: int | None = None,
        scope: str = MemoryScope.AGENT_PRIVATE.value,
        shared_with_agents: list[str] | None = None,
        derived_from_agents: list[str] | None = None,
        coordination_metadata: dict | None = None,
        memory_type: str = MemoryType.STANDARD.value,  # ACE Enhancement
        source_trajectory_id: str | None = None,  # ACE Enhancement
        error_pattern: str | None = None,  # ACE Enhancement
        session_id: str | None = None,  # Typed Memory
        entity_id: str | None = None,  # Typed Memory
        sequence_number: int | None = None,  # Typed Memory
    ) -> Memory:
        """Add a single memory."""
        memory_id = uuid4().hex

        # Compute expiration time upfront (avoids runtime TTL checks)
        expires_at = None
        if ttl_seconds is not None:
            expires_at = datetime.now(timezone.utc).replace(
                microsecond=0
            ) + timedelta(seconds=ttl_seconds)

        mem = Memory(
            id=memory_id,
            project_id=project_id,
            user_id=user_id,
            agent_id=agent_id,
            namespace=namespace,
            content=content,
            content_hash=content_hash(content),
            embedding=embedding,
            metadata_json=metadata or {},
            expires_at=expires_at,
            scope=scope,
            shared_with_agents=shared_with_agents or [],
            derived_from_agents=derived_from_agents or [],
            coordination_metadata=coordination_metadata or {},
            memory_type=memory_type,
            source_trajectory_id=source_trajectory_id,
            error_pattern=error_pattern,
            session_id=session_id,
            entity_id=entity_id,
            sequence_number=sequence_number,
        )

        try:
            with track_latency(OperationNames.MEMORY_ADD):
                db.add(mem)
                await db.flush()

                # Dual-write: populate join table for ACL
                if shared_with_agents:
                    for agent in shared_with_agents:
                        db.add(MemorySharedAgent(
                            memory_id=memory_id,
                            shared_agent_id=agent,
                            project_id=project_id,
                            namespace=namespace,
                        ))
                    await db.flush()

            record_operation(OperationNames.MEMORY_ADD, "success")
            return mem
        except Exception:
            record_operation(OperationNames.MEMORY_ADD, "error")
            raise

    @staticmethod
    async def add_batch(
        db: AsyncSession,
        memories: list[dict],
    ) -> list[Memory]:
        """
        Bulk insert memories.

        Uses PostgreSQL's multi-value INSERT for efficiency.
        """
        now = datetime.now(timezone.utc)
        objs = []

        for m in memories:
            ttl = m.get("ttl_seconds")
            expires_at = None
            if ttl is not None:
                expires_at = now + timedelta(seconds=ttl)

            obj = Memory(
                id=uuid4().hex,
                project_id=m["project_id"],
                user_id=m.get("user_id"),
                agent_id=m.get("agent_id"),
                namespace=m.get("namespace", "default"),
                content=m["content"],
                content_hash=content_hash(m["content"]),
                embedding=m["embedding"],
                metadata_json=m.get("metadata") or {},
                expires_at=expires_at,
                scope=m.get("scope", MemoryScope.AGENT_PRIVATE.value),
                shared_with_agents=m.get("shared_with_agents") or [],
                derived_from_agents=m.get("derived_from_agents") or [],
                coordination_metadata=m.get("coordination_metadata") or {},
                memory_type=m.get("memory_type", MemoryType.STANDARD.value),
                session_id=m.get("session_id"),
                entity_id=m.get("entity_id"),
                sequence_number=m.get("sequence_number"),
            )
            objs.append(obj)

        try:
            with track_latency(OperationNames.MEMORY_ADD_BATCH):
                db.add_all(objs)
                await db.flush()

                # Dual-write: populate join table for ACL
                for i, obj in enumerate(objs):
                    shared = memories[i].get("shared_with_agents") or []
                    for agent in shared:
                        db.add(MemorySharedAgent(
                            memory_id=obj.id,
                            shared_agent_id=agent,
                            project_id=obj.project_id,
                            namespace=obj.namespace,
                        ))
                if any(m.get("shared_with_agents") for m in memories):
                    await db.flush()

            record_operation(OperationNames.MEMORY_ADD_BATCH, "success")
            return objs
        except Exception:
            record_operation(OperationNames.MEMORY_ADD_BATCH, "error")
            raise

    @staticmethod
    async def semantic_search(
        db: AsyncSession,
        *,
        query_embedding: list[float],
        project_id: str,
        namespace: str = "default",
        user_id: str | None = None,
        agent_id: str | None = None,
        requesting_agent_id: str | None = None,  # For cross-agent access control
        target_agent_ids: list[str] | None = None,  # For cross-agent queries
        top_k: int = 10,
        min_score: float = 0.0,
        include_deprecated: bool = False,  # ACE Enhancement
        memory_types: list[str] | None = None,  # ACE Enhancement: filter by type
        requested_scope: str | None = None,
        min_effectiveness: float | None = None,
    ) -> tuple[list[tuple[Memory, float]], dict]:
        """
        Semantic search using pgvector's HNSW index.

        This is the CRITICAL fix from v0:
        - v0: Fetch 100+ rows, compute cosine similarity in Python → O(n)
        - v1: Use pgvector's <=> operator with HNSW index → O(log n)

        Query structure matters for pgvector:
        - Filters go in WHERE clause (not subquery)
        - ORDER BY embedding <=> query_embedding uses the HNSW index
        - LIMIT caps the ANN search, not post-filtering
        """
        # Build the embedding literal for pgvector
        f"[{','.join(str(x) for x in query_embedding)}]"

        # Base query with cosine distance (1 - similarity)
        # pgvector's <=> is cosine distance, so lower is better
        distance_expr = Memory.embedding.cosine_distance(query_embedding)

        # Start with mandatory filters
        conditions = [
            Memory.project_id == project_id,
            Memory.namespace == namespace,
            or_(
                Memory.expires_at.is_(None),
                Memory.expires_at > datetime.now(timezone.utc)
            ),
        ]

        # ACE Enhancement: Exclude deprecated by default
        if not include_deprecated:
            conditions.append(not_(Memory.is_deprecated))

        # ACE Enhancement: Filter by memory type
        if memory_types:
            conditions.append(Memory.memory_type.in_(memory_types))

        # Optional explicit scope request
        if requested_scope is not None:
            conditions.append(Memory.scope == requested_scope)

        # Optional user filter
        if user_id is not None:
            conditions.append(Memory.user_id == user_id)

        # Agent filtering based on query type
        if target_agent_ids is not None:
            # Cross-agent query: search specific agents
            conditions.append(Memory.agent_id.in_(target_agent_ids))
        elif agent_id is not None:
            # Single-agent query
            conditions.append(Memory.agent_id == agent_id)

        # Build scope-aware access control
        # This is the complex part: we need to filter based on scope + requesting_agent
        if requesting_agent_id is not None:
            # Can access if:
            # 1. Scope is GLOBAL, or
            # 2. Scope is AGENT_PRIVATE and agent_id matches, or
            # 3. Scope is AGENT_SHARED and (agent_id matches OR in memory_shared_agents join table)
            # Uses indexed join table for O(1) ACL lookups at scale
            shared_subquery = (
                select(MemorySharedAgent.memory_id)
                .where(MemorySharedAgent.shared_agent_id == requesting_agent_id)
            )

            scope_filter = or_(
                Memory.scope == MemoryScope.GLOBAL.value,
                and_(
                    Memory.scope == MemoryScope.AGENT_PRIVATE.value,
                    Memory.agent_id == requesting_agent_id
                ),
                and_(
                    Memory.scope == MemoryScope.AGENT_SHARED.value,
                    or_(
                        Memory.agent_id == requesting_agent_id,
                        Memory.id.in_(shared_subquery)
                    )
                ),
            )
            conditions.append(scope_filter)
        else:
            # No requesting agent = only global memories
            conditions.append(Memory.scope == MemoryScope.GLOBAL.value)

        effective_scope = "global_only"
        if requesting_agent_id is not None:
            effective_scope = "acl_global_private_shared"
            if target_agent_ids:
                effective_scope = "acl_targeted_agents"

        # Build the query
        # Key: ORDER BY distance LIMIT k uses the HNSW index efficiently
        stmt = (
            select(Memory, distance_expr.label("distance"))
            .where(and_(*conditions))
            .order_by(distance_expr)
            .limit(top_k)
        )

        query_start = time.monotonic()
        try:
            with track_latency(OperationNames.MEMORY_SEMANTIC_SEARCH):
                result = await db.execute(stmt)
                rows = result.all()
            record_operation(OperationNames.MEMORY_SEMANTIC_SEARCH, "success")
        except Exception:
            record_operation(OperationNames.MEMORY_SEMANTIC_SEARCH, "error")
            raise

        # Convert distance to similarity score (1 - distance for cosine)
        # Filter by min_score
        output = []
        for mem, distance in rows:
            score = 1.0 - distance
            if score >= min_score:
                output.append((mem, score))

        record_query_execution(
            source="semantic_search",
            duration_seconds=time.monotonic() - query_start,
            total_returned=len(output),
            requested_scope=requested_scope,
            effective_scope=effective_scope,
            memory_type=("multi" if memory_types and len(memory_types) > 1 else (memory_types[0] if memory_types else None)),
            min_effectiveness=min_effectiveness,
            target_agent_ids_used=bool(target_agent_ids),
            retrieved_scopes=[mem.scope for mem, _ in output],
            retrieved_agent_ids=[mem.agent_id for mem, _ in output if mem.agent_id],
        )

        return output, {
            "requested_scope": requested_scope,
            "effective_scope": effective_scope,
        }

    @staticmethod
    async def find_duplicates(
        db: AsyncSession,
        *,
        content_hash: str,
        project_id: str,
        namespace: str,
        user_id: str | None = None,
        agent_id: str | None = None,
    ) -> Memory | None:
        """
        Fast deduplication using content hash.

        v0 did semantic similarity for dedup (expensive).
        v1 uses content hash (O(1) with index).
        """
        conditions = [
            Memory.project_id == project_id,
            Memory.namespace == namespace,
            Memory.content_hash == content_hash,
        ]

        if user_id is not None:
            conditions.append(Memory.user_id == user_id)
        if agent_id is not None:
            conditions.append(Memory.agent_id == agent_id)

        stmt = select(Memory).where(and_(*conditions)).limit(1)
        try:
            with track_latency(OperationNames.MEMORY_FIND_DUPLICATE):
                result = await db.execute(stmt)
            record_operation(OperationNames.MEMORY_FIND_DUPLICATE, "success")
            return result.scalar_one_or_none()
        except Exception:
            record_operation(OperationNames.MEMORY_FIND_DUPLICATE, "error")
            raise

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        memory_id: str,
        project_id: str,
    ) -> Memory | None:
        """Get a memory by ID with project validation."""
        stmt = select(Memory).where(
            Memory.id == memory_id,
            Memory.project_id == project_id,
        )
        try:
            with track_latency(OperationNames.MEMORY_GET_BY_ID):
                result = await db.execute(stmt)
            record_operation(OperationNames.MEMORY_GET_BY_ID, "success")
            return result.scalar_one_or_none()
        except Exception:
            record_operation(OperationNames.MEMORY_GET_BY_ID, "error")
            raise

    @staticmethod
    async def delete(
        db: AsyncSession,
        memory_id: str,
        project_id: str,
    ) -> bool:
        """Delete a memory. Returns True if deleted."""
        stmt = delete(Memory).where(
            Memory.id == memory_id,
            Memory.project_id == project_id,
        ).returning(Memory.id)

        try:
            with track_latency(OperationNames.MEMORY_DELETE):
                result = await db.execute(stmt)
            deleted = result.scalar_one_or_none() is not None
            record_operation(OperationNames.MEMORY_DELETE, "success" if deleted else "error")
            return deleted
        except Exception:
            record_operation(OperationNames.MEMORY_DELETE, "error")
            raise

    @staticmethod
    async def cleanup_expired(db: AsyncSession, batch_size: int = 1000) -> int:
        """
        Delete expired memories.

        Run this periodically (e.g., every 5 minutes via cron/scheduler).
        Uses LIMIT to avoid long-running transactions.
        """
        now = datetime.now(timezone.utc)

        # Find IDs to delete (subquery)
        subquery = (
            select(Memory.id)
            .where(
                Memory.expires_at.isnot(None),
                Memory.expires_at <= now,
            )
            .limit(batch_size)
        )

        # Delete by IDs
        stmt = delete(Memory).where(Memory.id.in_(subquery))
        result = await db.execute(stmt)

        return result.rowcount

    @staticmethod
    async def get_agent_memories_for_handoff(
        db: AsyncSession,
        *,
        project_id: str,
        source_agent_id: str,
        namespace: str = "default",
        user_id: str | None = None,
        task_embedding: list[float] | None = None,
        max_memories: int = 20,
    ) -> list[tuple[Memory, float | None]]:
        """
        Get memories for agent handoff.

        If task_embedding provided, rank by relevance.
        Otherwise, return most recent.
        """
        conditions = [
            Memory.project_id == project_id,
            Memory.agent_id == source_agent_id,
            Memory.namespace == namespace,
            or_(
                Memory.expires_at.is_(None),
                Memory.expires_at > datetime.now(timezone.utc)
            ),
        ]

        if user_id is not None:
            conditions.append(Memory.user_id == user_id)

        if task_embedding is not None:
            # Rank by semantic similarity to task
            distance_expr = Memory.embedding.cosine_distance(task_embedding)
            stmt = (
                select(Memory, (1.0 - distance_expr).label("score"))
                .where(and_(*conditions))
                .order_by(distance_expr)
                .limit(max_memories)
            )
        else:
            # Rank by recency
            stmt = (
                select(Memory, text("NULL::float as score"))
                .where(and_(*conditions))
                .order_by(Memory.created_at.desc())
                .limit(max_memories)
            )

        try:
            with track_latency(OperationNames.MEMORY_GET_HANDOFF):
                result = await db.execute(stmt)
            record_operation(OperationNames.MEMORY_GET_HANDOFF, "success")
            return [(mem, score) for mem, score in result.all()]
        except Exception:
            record_operation(OperationNames.MEMORY_GET_HANDOFF, "error")
            raise

    @staticmethod
    async def get_session_timeline(
        db: AsyncSession,
        *,
        project_id: str,
        session_id: str,
        namespace: str = "default",
        include_deprecated: bool = False,
        limit: int = 100,
    ) -> list[Memory]:
        """
        Get episodic memories for a session ordered by sequence_number then created_at.

        Uses the ix_memories_session partial index for efficient lookups.
        """
        conditions = [
            Memory.project_id == project_id,
            Memory.session_id == session_id,
            Memory.namespace == namespace,
        ]
        if not include_deprecated:
            conditions.append(not_(Memory.is_deprecated))

        stmt = (
            select(Memory)
            .where(and_(*conditions))
            .order_by(
                Memory.sequence_number.asc().nulls_last(),
                Memory.created_at.asc(),
            )
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_entity_facts(
        db: AsyncSession,
        *,
        project_id: str,
        entity_id: str,
        namespace: str = "default",
        include_deprecated: bool = False,
        limit: int = 100,
    ) -> list[Memory]:
        """
        Get semantic memories for an entity ordered by created_at desc.

        Uses the ix_memories_entity partial index for efficient lookups.
        """
        conditions = [
            Memory.project_id == project_id,
            Memory.entity_id == entity_id,
            Memory.namespace == namespace,
        ]
        if not include_deprecated:
            conditions.append(not_(Memory.is_deprecated))

        stmt = (
            select(Memory)
            .where(and_(*conditions))
            .order_by(Memory.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
