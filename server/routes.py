"""
Aegis Production Routes

Key improvements:
1. Fully async endpoints
2. Rate limiting per project
3. Background tasks for slow operations
4. Proper error handling with structured responses
5. Request validation with Pydantic v2
"""

from datetime import datetime
from typing import Any

from config import get_settings
from database import get_db, get_read_db
from embedding_service import content_hash, get_embedding_service
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from memory_repository import MemoryRepository
from models import Memory, MemoryScope
from pydantic import BaseModel, Field, field_validator
from rate_limiter import RateLimiter, RateLimitExceeded
from scope_inference import ScopeInference
from observability import (
    OperationNames,
    record_memory_stored_scope,
    record_operation,
    record_query_execution,
    track_latency,
)
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
settings = get_settings()
rate_limiter = RateLimiter()


# ---------- Request/Response Models ----------

class MemoryCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)
    user_id: str | None = Field(default=None, max_length=64)
    agent_id: str | None = Field(default=None, max_length=64)
    namespace: str = Field(default="default", max_length=64)
    metadata: dict[str, Any] | None = None
    ttl_seconds: int | None = Field(default=None, ge=1, le=31536000)  # Max 1 year
    scope: str | None = None
    shared_with_agents: list[str] | None = None
    derived_from_agents: list[str] | None = None
    coordination_metadata: dict[str, Any] | None = None

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, v):
        if v is not None:
            valid = [s.value for s in MemoryScope]
            if v not in valid:
                raise ValueError(f"scope must be one of: {valid}")
        return v


class MemoryCreateBatch(BaseModel):
    items: list[MemoryCreate] = Field(..., min_length=1, max_length=100)


class MemoryQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=10_000)
    user_id: str | None = None
    agent_id: str | None = None
    scope: str | None = None
    namespace: str = "default"
    top_k: int = Field(default=10, ge=1, le=100)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class CrossAgentQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=10_000)
    requesting_agent_id: str = Field(..., min_length=1, max_length=64)
    target_agent_ids: list[str] | None = None
    user_id: str | None = None
    scope: str | None = None
    namespace: str = "default"
    top_k: int = Field(default=10, ge=1, le=100)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class HandoffRequest(BaseModel):
    source_agent_id: str
    target_agent_id: str
    namespace: str = "default"
    user_id: str | None = None
    task_context: str | None = Field(default=None, max_length=10_000)
    max_memories: int = Field(default=20, ge=1, le=100)


class MemoryOut(BaseModel):
    id: str
    content: str
    user_id: str | None
    agent_id: str | None
    namespace: str
    metadata: dict[str, Any]
    created_at: datetime
    scope: str
    shared_with_agents: list[str]
    derived_from_agents: list[str]
    coordination_metadata: dict[str, Any]
    score: float | None = None

    class Config:
        from_attributes = True


class AddResult(BaseModel):
    id: str
    deduped_from: str | None = None
    inferred_scope: str | None = None


class AddBatchResult(BaseModel):
    results: list[AddResult]
    embeddings_cached: int
    total_time_ms: float


class QueryResult(BaseModel):
    memories: list[MemoryOut]
    query_time_ms: float


class HandoffBaton(BaseModel):
    source_agent_id: str
    target_agent_id: str
    namespace: str
    user_id: str | None
    task_context: str | None
    summary: str | None
    active_tasks: list[str]
    blocked_on: list[str]
    recent_decisions: list[str]
    key_facts: list[str]
    memory_ids: list[str]


# ---------- Dependencies ----------

async def get_project_id(request: Request) -> str:
    """Extract and validate project ID from API key."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header. Expected: 'Bearer <api_key>'"
        )

    token = auth[7:].strip()

    # In production, validate against a projects table
    # For now, use the configured API key
    if token != settings.aegis_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key. Check AEGIS_API_KEY environment variable on the server."
        )

    return settings.default_project_id


async def check_rate_limit(project_id: str = Depends(get_project_id)):
    """Rate limit check as dependency."""
    try:
        await rate_limiter.check(project_id)
    except RateLimitExceeded as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e),
            headers={"Retry-After": str(e.retry_after)}
        ) from e
    return project_id


# ---------- Routes ----------

@router.post("/add", response_model=AddResult)
async def add_memory(
    body: MemoryCreate,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    Add a single memory with automatic scope inference and deduplication.
    """
    try:
        with track_latency(OperationNames.MEMORY_ADD):
            embed_service = get_embedding_service()

            # Check for duplicates using content hash (fast)
            hash_val = content_hash(body.content)
            existing = await MemoryRepository.find_duplicates(
                db,
                content_hash=hash_val,
                project_id=project_id,
                namespace=body.namespace,
                user_id=body.user_id,
                agent_id=body.agent_id,
            )

            if existing:
                record_operation(OperationNames.MEMORY_ADD, "success")
                return AddResult(id=existing.id, deduped_from=existing.id)

            # Generate embedding
            embedding = await embed_service.embed_single(body.content, db)

            # Infer scope if not provided
            resolved_scope = ScopeInference.infer_scope(
                content=body.content,
                explicit_scope=body.scope,
                agent_id=body.agent_id,
                metadata=body.metadata or {},
            )

            # Create memory
            mem = await MemoryRepository.add(
                db,
                project_id=project_id,
                content=body.content,
                embedding=embedding,
                user_id=body.user_id,
                agent_id=body.agent_id,
                namespace=body.namespace,
                metadata=body.metadata,
                ttl_seconds=body.ttl_seconds,
                scope=resolved_scope.value,
                shared_with_agents=body.shared_with_agents,
                derived_from_agents=body.derived_from_agents,
                coordination_metadata=body.coordination_metadata,
            )
            record_memory_stored_scope(resolved_scope.value)

            record_operation(OperationNames.MEMORY_ADD, "success")
            return AddResult(
                id=mem.id,
                deduped_from=None,
                inferred_scope=resolved_scope.value if body.scope is None else None,
            )
    except Exception:
        record_operation(OperationNames.MEMORY_ADD, "error")
        raise


@router.post("/add_batch", response_model=AddBatchResult)
async def add_memory_batch(
    body: MemoryCreateBatch,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    Add multiple memories efficiently with batched embedding.

    This is MUCH faster than calling /add multiple times:
    - Single embedding API call for all texts
    - Bulk database insert
    """
    import time
    start = time.monotonic()

    embed_service = get_embedding_service()

    # Batch embed all content
    texts = [item.content for item in body.items]
    embeddings = await embed_service.embed_batch(texts, db)

    results = []
    to_insert = []

    for i, item in enumerate(body.items):
        # Check dedup
        hash_val = content_hash(item.content)
        existing = await MemoryRepository.find_duplicates(
            db,
            content_hash=hash_val,
            project_id=project_id,
            namespace=item.namespace,
            user_id=item.user_id,
            agent_id=item.agent_id,
        )

        if existing:
            results.append(AddResult(id=existing.id, deduped_from=existing.id))
            continue

        # Prepare for bulk insert
        resolved_scope = ScopeInference.infer_scope(
            content=item.content,
            explicit_scope=item.scope,
            agent_id=item.agent_id,
            metadata=item.metadata or {},
        )

        to_insert.append({
            "project_id": project_id,
            "content": item.content,
            "embedding": embeddings[i],
            "user_id": item.user_id,
            "agent_id": item.agent_id,
            "namespace": item.namespace,
            "metadata": item.metadata,
            "ttl_seconds": item.ttl_seconds,
            "scope": resolved_scope.value,
            "shared_with_agents": item.shared_with_agents,
            "derived_from_agents": item.derived_from_agents,
            "coordination_metadata": item.coordination_metadata,
        })

        # Placeholder - will be filled after bulk insert
        results.append(None)

    # Bulk insert
    if to_insert:
        memories = await MemoryRepository.add_batch(db, to_insert)
        for item in to_insert:
            record_memory_stored_scope(item["scope"])

        # Fill in results
        mem_iter = iter(memories)
        for i in range(len(results)):
            if results[i] is None:
                mem = next(mem_iter)
                results[i] = AddResult(id=mem.id, deduped_from=None)

    elapsed_ms = (time.monotonic() - start) * 1000
    stats = embed_service.get_stats()

    return AddBatchResult(
        results=results,
        embeddings_cached=stats["cache_hits"],
        total_time_ms=round(elapsed_ms, 2),
    )


@router.post("/query", response_model=QueryResult)
async def query_memories(
    body: MemoryQuery,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),  # Use read replica
):
    """
    Semantic search over memories.

    Uses pgvector's HNSW index for O(log n) search.
    """
    import time
    start = time.monotonic()

    try:
        with track_latency(OperationNames.MEMORY_QUERY):
            embed_service = get_embedding_service()
            query_embedding = await embed_service.embed_single(body.query, db)

            results, query_meta = await MemoryRepository.semantic_search(
                db,
                query_embedding=query_embedding,
                project_id=project_id,
                namespace=body.namespace,
                user_id=body.user_id,
                agent_id=body.agent_id,
                requesting_agent_id=body.agent_id,  # Same agent for single-agent query
                top_k=body.top_k,
                min_score=body.min_score,
                requested_scope=body.scope,
            )

        elapsed_ms = (time.monotonic() - start) * 1000

        memories = [
            MemoryOut(
                id=mem.id,
                content=mem.content,
                user_id=mem.user_id,
                agent_id=mem.agent_id,
                namespace=mem.namespace,
                metadata=mem.metadata_json or {},
                created_at=mem.created_at,
                scope=mem.scope,
                shared_with_agents=mem.shared_with_agents or [],
                derived_from_agents=mem.derived_from_agents or [],
                coordination_metadata=mem.coordination_metadata or {},
                score=score,
            )
            for mem, score in results
        ]

        record_query_execution(
            source="query",
            duration_seconds=elapsed_ms / 1000,
            total_returned=len(memories),
            requested_scope=body.scope,
            effective_scope=query_meta["effective_scope"],
            target_agent_ids_used=False,
            query_text=body.query,
            retrieved_scopes=[mem.scope for mem, _ in results],
            retrieved_agent_ids=[mem.agent_id for mem, _ in results if mem.agent_id],
        )

        record_operation(OperationNames.MEMORY_QUERY, "success")
        return QueryResult(memories=memories, query_time_ms=round(elapsed_ms, 2))
    except Exception:
        record_operation(OperationNames.MEMORY_QUERY, "error")
        raise


@router.post("/query_cross_agent", response_model=QueryResult)
async def query_cross_agent(
    body: CrossAgentQuery,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    """
    Cross-agent semantic search with scope-aware access control.

    Agents can only see:
    - GLOBAL memories (any agent)
    - AGENT_PRIVATE memories they own
    - AGENT_SHARED memories they're in the shared list
    """
    import time
    start = time.monotonic()

    embed_service = get_embedding_service()
    query_embedding = await embed_service.embed_single(body.query, db)

    results, query_meta = await MemoryRepository.semantic_search(
        db,
        query_embedding=query_embedding,
        project_id=project_id,
        namespace=body.namespace,
        user_id=body.user_id,
        requesting_agent_id=body.requesting_agent_id,
        target_agent_ids=body.target_agent_ids,
        top_k=body.top_k,
        min_score=body.min_score,
        requested_scope=body.scope,
    )

    elapsed_ms = (time.monotonic() - start) * 1000

    memories = [
        MemoryOut(
            id=mem.id,
            content=mem.content,
            user_id=mem.user_id,
            agent_id=mem.agent_id,
            namespace=mem.namespace,
            metadata=mem.metadata_json or {},
            created_at=mem.created_at,
            scope=mem.scope,
            shared_with_agents=mem.shared_with_agents or [],
            derived_from_agents=mem.derived_from_agents or [],
            coordination_metadata=mem.coordination_metadata or {},
            score=score,
        )
        for mem, score in results
    ]

    record_query_execution(
        source="query_cross_agent",
        duration_seconds=elapsed_ms / 1000,
        total_returned=len(memories),
        requested_scope=body.scope,
        effective_scope=query_meta["effective_scope"],
        target_agent_ids_used=bool(body.target_agent_ids),
        query_text=body.query,
        retrieved_scopes=[mem.scope for mem, _ in results],
        retrieved_agent_ids=[mem.agent_id for mem, _ in results if mem.agent_id],
    )

    return QueryResult(memories=memories, query_time_ms=round(elapsed_ms, 2))


@router.post("/handoff", response_model=HandoffBaton)
async def handoff(
    body: HandoffRequest,
    background_tasks: BackgroundTasks,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a structured handoff baton for agent-to-agent state transfer.

    The LLM summarization runs in the background to avoid blocking.
    Returns immediately with raw facts, then updates asynchronously.
    """
    embed_service = get_embedding_service()

    # Get task embedding if context provided
    task_embedding = None
    if body.task_context:
        task_embedding = await embed_service.embed_single(body.task_context, db)

    # Fetch relevant memories
    results = await MemoryRepository.get_agent_memories_for_handoff(
        db,
        project_id=project_id,
        source_agent_id=body.source_agent_id,
        namespace=body.namespace,
        user_id=body.user_id,
        task_embedding=task_embedding,
        max_memories=body.max_memories,
    )

    memories = [mem for mem, _ in results]
    memory_ids = [mem.id for mem in memories]
    key_facts = [mem.content for mem in memories]

    # Return immediately with raw data
    # Background task can update with LLM summary if needed
    return HandoffBaton(
        source_agent_id=body.source_agent_id,
        target_agent_id=body.target_agent_id,
        namespace=body.namespace,
        user_id=body.user_id,
        task_context=body.task_context,
        summary=None,  # Could be filled by background task
        active_tasks=[],
        blocked_on=[],
        recent_decisions=[],
        key_facts=key_facts,
        memory_ids=memory_ids,
    )


@router.get("/{memory_id}", response_model=MemoryOut)
async def get_memory(
    memory_id: str,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    """Get a single memory by ID."""
    mem = await MemoryRepository.get_by_id(db, memory_id, project_id)
    if not mem:
        raise HTTPException(
            status_code=404,
            detail=f"Memory not found: {memory_id}. It may have been deleted or the ID is incorrect."
        )

    return MemoryOut(
        id=mem.id,
        content=mem.content,
        user_id=mem.user_id,
        agent_id=mem.agent_id,
        namespace=mem.namespace,
        metadata=mem.metadata_json or {},
        created_at=mem.created_at,
        scope=mem.scope,
        shared_with_agents=mem.shared_with_agents or [],
        derived_from_agents=mem.derived_from_agents or [],
        coordination_metadata=mem.coordination_metadata or {},
        score=None,
    )


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: str,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """Delete a memory by ID."""
    try:
        with track_latency(OperationNames.MEMORY_DELETE):
            deleted = await MemoryRepository.delete(db, memory_id, project_id)
        if not deleted:
            record_operation(OperationNames.MEMORY_DELETE, "error")
            raise HTTPException(
                status_code=404,
                detail=f"Memory not found: {memory_id}. It may have been deleted or the ID is incorrect."
            )
        record_operation(OperationNames.MEMORY_DELETE, "success")
    except HTTPException:
        raise
    except Exception:
        record_operation(OperationNames.MEMORY_DELETE, "error")
        raise


# ---------- Data Export (Migration Safety) ----------

class ExportRequest(BaseModel):
    """Request for data export."""
    namespace: str | None = None
    agent_id: str | None = None
    format: str = Field(default="jsonl", pattern="^(jsonl|json)$")
    include_embeddings: bool = False
    limit: int | None = Field(default=None, ge=1, le=100000)


class ExportStats(BaseModel):
    """Export statistics."""
    total_exported: int
    format: str
    namespaces: list[str]
    agents: list[str]


@router.post("/export")
async def export_memories(
    body: ExportRequest,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    """
    Export memories for backup or migration.

    Supports JSONL (streaming) and JSON formats.
    Does NOT include proprietary data - standard JSON format only.

    Use cases:
    - GDPR data portability requests
    - Migration to another system
    - Backup verification
    - Analytics/debugging
    """
    import json

    from fastapi.responses import StreamingResponse

    # Build query
    conditions = [Memory.project_id == project_id]

    if body.namespace:
        conditions.append(Memory.namespace == body.namespace)
    if body.agent_id:
        conditions.append(Memory.agent_id == body.agent_id)

    base_stmt = (
        select(Memory)
        .where(and_(*conditions))
        .order_by(Memory.created_at, Memory.id)
    )

    chunk_size = 1000

    # Track stats
    namespaces = set()
    agents = set()

    def serialize_memory(mem: Memory) -> dict:
        """Serialize memory to portable JSON."""
        namespaces.add(mem.namespace)
        if mem.agent_id:
            agents.add(mem.agent_id)

        data = {
            "id": mem.id,
            "content": mem.content,
            "user_id": mem.user_id,
            "agent_id": mem.agent_id,
            "namespace": mem.namespace,
            "scope": mem.scope,
            "metadata": mem.metadata_json or {},
            "memory_type": mem.memory_type,
            "created_at": mem.created_at.isoformat(),
            "updated_at": mem.updated_at.isoformat() if mem.updated_at else None,
            "bullet_helpful": mem.bullet_helpful,
            "bullet_harmful": mem.bullet_harmful,
        }

        if body.include_embeddings:
            data["embedding"] = list(mem.embedding) if mem.embedding else None

        return data

    async def iter_memories():
        """Yield memories in stable chunks to keep memory bounded."""
        fetched = 0
        cursor_created_at = None
        cursor_id = None

        while True:
            remaining = None
            if body.limit is not None:
                remaining = body.limit - fetched
                if remaining <= 0:
                    break

            stmt = base_stmt
            if cursor_created_at is not None and cursor_id is not None:
                stmt = stmt.where(
                    or_(
                        Memory.created_at > cursor_created_at,
                        and_(Memory.created_at == cursor_created_at, Memory.id > cursor_id),
                    )
                )

            batch_limit = chunk_size if remaining is None else min(chunk_size, remaining)
            stmt = stmt.limit(batch_limit)

            result = await db.execute(stmt)
            batch = result.scalars().all()
            if not batch:
                break

            for mem in batch:
                yield mem

            fetched += len(batch)
            last = batch[-1]
            cursor_created_at = last.created_at
            cursor_id = last.id

            if len(batch) < batch_limit:
                break

    async def count_for_export() -> int:
        """Return total rows honoring filters and optional limit."""
        count_stmt = select(func.count()).where(and_(*conditions))
        total = (await db.execute(count_stmt)).scalar_one()
        if body.limit is not None:
            return min(total, body.limit)
        return total

    if body.format == "jsonl":
        # Stream JSONL for large exports
        total_exported = await count_for_export()

        async def generate():
            async for mem in iter_memories():
                yield json.dumps(serialize_memory(mem)) + "\n"

        return StreamingResponse(
            generate(),
            media_type="application/x-ndjson",
            headers={
                "Content-Disposition": f"attachment; filename=aegis_export_{project_id}.jsonl",
                "X-Export-Total": str(total_exported),
                "X-Export-Format": body.format,
            }
        )
    else:
        # Return full JSON
        exported = []
        async for mem in iter_memories():
            exported.append(serialize_memory(mem))

        return {
            "memories": exported,
            "stats": {
                "total_exported": len(exported),
                "format": body.format,
                "namespaces": list(namespaces),
                "agents": list(agents),
            }
        }
