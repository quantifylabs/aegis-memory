"""ACE domain service.

Encapsulates business logic for ACE operations (voting, delta, reflection, etc.).
Does NOT call commit() -- that's the route/dependency's job.
"""
from ace_repository import ACERepository
from embedding_service import get_embedding_service
from models import MemoryScope, MemoryType
from scope_inference import ScopeInference
from sqlalchemy.ext.asyncio import AsyncSession


class ACEService:
    """Business logic for ACE operations."""

    @staticmethod
    async def create_reflection_with_embedding(
        db: AsyncSession,
        *,
        project_id: str,
        content: str,
        agent_id: str,
        user_id: str | None = None,
        namespace: str = "default",
        scope: str | None = None,
        metadata: dict | None = None,
        source_trajectory_id: str | None = None,
        error_pattern: str | None = None,
    ):
        """Create a reflection with embedding generation and scope inference."""
        embed_service = get_embedding_service()
        embedding = await embed_service.embed_single(content, db)

        resolved_scope = ScopeInference.infer_scope(
            content=content,
            explicit_scope=scope or MemoryScope.GLOBAL.value,
            agent_id=agent_id,
            metadata=metadata or {},
        )

        return await ACERepository.create_reflection(
            db,
            project_id=project_id,
            content=content,
            embedding=embedding,
            agent_id=agent_id,
            user_id=user_id,
            namespace=namespace,
            scope=resolved_scope.value,
            metadata=metadata,
            source_trajectory_id=source_trajectory_id,
            error_pattern=error_pattern,
        )
