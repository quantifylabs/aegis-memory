"""Memory domain service.

Encapsulates business logic for memory operations.
Does NOT call commit() -- that's the route/dependency's job.
"""

from embedding_service import content_hash, get_embedding_service
from memory_repository import MemoryRepository
from models import MemoryScope
from scope_inference import ScopeInference
from sqlalchemy.ext.asyncio import AsyncSession


class MemoryService:
    """Business logic for memory CRUD operations."""

    @staticmethod
    async def add_with_dedup(
        db: AsyncSession,
        *,
        project_id: str,
        content: str,
        user_id: str | None = None,
        agent_id: str | None = None,
        namespace: str = "default",
        metadata: dict | None = None,
        ttl_seconds: int | None = None,
        scope: str | None = None,
        shared_with_agents: list[str] | None = None,
        derived_from_agents: list[str] | None = None,
        coordination_metadata: dict | None = None,
    ):
        """Add a memory with deduplication and scope inference.

        Returns (memory, deduped_from, inferred_scope).
        """
        embed_service = get_embedding_service()

        # Check dedup
        hash_val = content_hash(content)
        existing = await MemoryRepository.find_duplicates(
            db,
            content_hash=hash_val,
            project_id=project_id,
            namespace=namespace,
            user_id=user_id,
            agent_id=agent_id,
        )
        if existing:
            return existing, existing.id, None

        # Generate embedding
        embedding = await embed_service.embed_single(content, db)

        # Infer scope
        resolved_scope = ScopeInference.infer_scope(
            content=content,
            explicit_scope=scope,
            agent_id=agent_id,
            metadata=metadata or {},
        )

        mem = await MemoryRepository.add(
            db,
            project_id=project_id,
            content=content,
            embedding=embedding,
            user_id=user_id,
            agent_id=agent_id,
            namespace=namespace,
            metadata=metadata,
            ttl_seconds=ttl_seconds,
            scope=resolved_scope.value,
            shared_with_agents=shared_with_agents,
            derived_from_agents=derived_from_agents,
            coordination_metadata=coordination_metadata,
        )
        inferred = resolved_scope.value if scope is None else None
        return mem, None, inferred
