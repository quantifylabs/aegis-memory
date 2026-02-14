"""
Typed Memory Router (~280 lines)

Cognitive memory types: episodic, semantic, procedural, control.
Handles: /episodic, /semantic, /procedural, /control, /query,
         /episodic/session/{session_id}, /semantic/entity/{entity_id}
"""

import time
from datetime import datetime
from typing import Any

from embedding_service import content_hash, get_embedding_service
from event_repository import EventRepository
from fastapi import APIRouter, Depends, Query
from memory_repository import MemoryRepository
from models import Memory, MemoryEventType, MemoryScope, MemoryType
from pydantic import BaseModel, Field
from scope_inference import ScopeInference
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies.auth import check_rate_limit
from api.dependencies.database import get_db, get_read_db

router = APIRouter()


# ---------- Pydantic Models ----------

class EpisodicCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)
    agent_id: str = Field(..., min_length=1, max_length=64)
    session_id: str = Field(..., min_length=1, max_length=64)
    sequence_number: int | None = Field(default=None, ge=0)
    user_id: str | None = Field(default=None, max_length=64)
    namespace: str = Field(default="default", max_length=64)
    metadata: dict[str, Any] | None = None
    ttl_seconds: int | None = Field(default=None, ge=1, le=31536000)


class SemanticCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)
    entity_id: str | None = Field(default=None, max_length=128)
    agent_id: str | None = Field(default=None, max_length=64)
    user_id: str | None = Field(default=None, max_length=64)
    namespace: str = Field(default="default", max_length=64)
    metadata: dict[str, Any] | None = None
    ttl_seconds: int | None = Field(default=None, ge=1, le=31536000)


class ProceduralCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)
    agent_id: str = Field(..., min_length=1, max_length=64)
    trigger_conditions: list[str] | None = None
    steps: list[str] | None = None
    user_id: str | None = Field(default=None, max_length=64)
    namespace: str = Field(default="default", max_length=64)
    metadata: dict[str, Any] | None = None
    ttl_seconds: int | None = Field(default=None, ge=1, le=31536000)


class ControlCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)
    agent_id: str = Field(..., min_length=1, max_length=64)
    error_pattern: str | None = Field(default=None, max_length=128)
    severity: str | None = Field(default=None, max_length=32)
    source_trajectory_id: str | None = Field(default=None, max_length=64)
    user_id: str | None = Field(default=None, max_length=64)
    namespace: str = Field(default="default", max_length=64)
    metadata: dict[str, Any] | None = None
    ttl_seconds: int | None = Field(default=None, ge=1, le=31536000)


class TypedQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=10_000)
    memory_types: list[str] = Field(..., min_length=1)
    session_id: str | None = None
    entity_id: str | None = None
    agent_id: str | None = None
    user_id: str | None = None
    namespace: str = "default"
    top_k: int = Field(default=10, ge=1, le=100)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class TypedMemoryOut(BaseModel):
    id: str
    content: str
    memory_type: str
    user_id: str | None
    agent_id: str | None
    namespace: str
    metadata: dict[str, Any]
    created_at: datetime
    scope: str
    shared_with_agents: list[str]
    derived_from_agents: list[str]
    coordination_metadata: dict[str, Any]
    session_id: str | None = None
    entity_id: str | None = None
    sequence_number: int | None = None
    score: float | None = None

    class Config:
        from_attributes = True


class TypedAddResult(BaseModel):
    id: str
    memory_type: str
    scope: str
    deduped_from: str | None = None


class TypedQueryResult(BaseModel):
    memories: list[TypedMemoryOut]
    query_time_ms: float


class SessionTimelineResult(BaseModel):
    session_id: str
    memories: list[TypedMemoryOut]
    count: int


class EntityFactsResult(BaseModel):
    entity_id: str
    memories: list[TypedMemoryOut]
    count: int


# ---------- Helpers ----------

def _mem_to_typed_out(mem: Memory, score: float | None = None) -> TypedMemoryOut:
    return TypedMemoryOut(
        id=mem.id,
        content=mem.content,
        memory_type=mem.memory_type,
        user_id=mem.user_id,
        agent_id=mem.agent_id,
        namespace=mem.namespace,
        metadata=mem.metadata_json or {},
        created_at=mem.created_at,
        scope=mem.scope,
        shared_with_agents=mem.shared_with_agents or [],
        derived_from_agents=mem.derived_from_agents or [],
        coordination_metadata=mem.coordination_metadata or {},
        session_id=mem.session_id,
        entity_id=mem.entity_id,
        sequence_number=mem.sequence_number,
        score=score,
    )


async def _create_typed_memory(
    db: AsyncSession,
    project_id: str,
    *,
    content: str,
    memory_type: MemoryType,
    default_scope: MemoryScope,
    agent_id: str | None = None,
    user_id: str | None = None,
    namespace: str = "default",
    metadata: dict | None = None,
    ttl_seconds: int | None = None,
    session_id: str | None = None,
    entity_id: str | None = None,
    sequence_number: int | None = None,
    source_trajectory_id: str | None = None,
    error_pattern: str | None = None,
) -> TypedAddResult:
    """Shared helper for all typed memory creation endpoints."""
    embed_service = get_embedding_service()

    # Dedup check
    hash_val = content_hash(content)
    existing = await MemoryRepository.find_duplicates(
        db, content_hash=hash_val, project_id=project_id,
        namespace=namespace, user_id=user_id, agent_id=agent_id,
    )
    if existing:
        return TypedAddResult(
            id=existing.id, memory_type=existing.memory_type,
            scope=existing.scope, deduped_from=existing.id,
        )

    embedding = await embed_service.embed_single(content, db)
    resolved_scope = ScopeInference.infer_scope(
        content=content, explicit_scope=default_scope.value,
        agent_id=agent_id, metadata=metadata or {},
    )

    mem = await MemoryRepository.add(
        db, project_id=project_id, content=content,
        embedding=embedding, user_id=user_id, agent_id=agent_id,
        namespace=namespace, metadata=metadata, ttl_seconds=ttl_seconds,
        scope=resolved_scope.value, memory_type=memory_type.value,
        session_id=session_id, entity_id=entity_id,
        sequence_number=sequence_number,
        source_trajectory_id=source_trajectory_id,
        error_pattern=error_pattern,
    )

    await EventRepository.create_event(
        db, memory_id=mem.id, project_id=project_id,
        namespace=mem.namespace, agent_id=mem.agent_id,
        event_type=MemoryEventType.CREATED.value,
        event_payload={"source": f"typed_{memory_type.value}"},
    )

    return TypedAddResult(
        id=mem.id, memory_type=mem.memory_type, scope=mem.scope,
    )


# ---------- Endpoints ----------

@router.post("/episodic", response_model=TypedAddResult)
async def create_episodic(
    body: EpisodicCreate,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """Store an episodic memory (time-ordered interaction trace)."""
    return await _create_typed_memory(
        db, project_id,
        content=body.content,
        memory_type=MemoryType.EPISODIC,
        default_scope=MemoryScope.AGENT_PRIVATE,
        agent_id=body.agent_id,
        user_id=body.user_id,
        namespace=body.namespace,
        metadata=body.metadata,
        ttl_seconds=body.ttl_seconds,
        session_id=body.session_id,
        sequence_number=body.sequence_number,
    )


@router.post("/semantic", response_model=TypedAddResult)
async def create_semantic(
    body: SemanticCreate,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """Store a semantic memory (fact, preference, knowledge)."""
    return await _create_typed_memory(
        db, project_id,
        content=body.content,
        memory_type=MemoryType.SEMANTIC,
        default_scope=MemoryScope.GLOBAL,
        agent_id=body.agent_id,
        user_id=body.user_id,
        namespace=body.namespace,
        metadata=body.metadata,
        ttl_seconds=body.ttl_seconds,
        entity_id=body.entity_id,
    )


@router.post("/procedural", response_model=TypedAddResult)
async def create_procedural(
    body: ProceduralCreate,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """Store a procedural memory (workflow, strategy, reusable pattern)."""
    metadata = body.metadata or {}
    if body.trigger_conditions:
        metadata["trigger_conditions"] = body.trigger_conditions
    if body.steps:
        metadata["steps"] = body.steps

    return await _create_typed_memory(
        db, project_id,
        content=body.content,
        memory_type=MemoryType.PROCEDURAL,
        default_scope=MemoryScope.GLOBAL,
        agent_id=body.agent_id,
        user_id=body.user_id,
        namespace=body.namespace,
        metadata=metadata,
        ttl_seconds=body.ttl_seconds,
    )


@router.post("/control", response_model=TypedAddResult)
async def create_control(
    body: ControlCreate,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """Store a control memory (meta-rule, error pattern, constraint)."""
    metadata = body.metadata or {}
    if body.severity:
        metadata["severity"] = body.severity

    return await _create_typed_memory(
        db, project_id,
        content=body.content,
        memory_type=MemoryType.CONTROL,
        default_scope=MemoryScope.GLOBAL,
        agent_id=body.agent_id,
        user_id=body.user_id,
        namespace=body.namespace,
        metadata=metadata,
        ttl_seconds=body.ttl_seconds,
        source_trajectory_id=body.source_trajectory_id,
        error_pattern=body.error_pattern,
    )


@router.post("/query", response_model=TypedQueryResult)
async def typed_query(
    body: TypedQuery,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """Type-filtered semantic search across cognitive memory types."""
    start = time.monotonic()
    embed_service = get_embedding_service()
    query_embedding = await embed_service.embed_single(body.query, db)

    results, _ = await MemoryRepository.semantic_search(
        db,
        query_embedding=query_embedding,
        project_id=project_id,
        namespace=body.namespace,
        user_id=body.user_id,
        agent_id=body.agent_id,
        requesting_agent_id=body.agent_id,
        top_k=body.top_k,
        min_score=body.min_score,
        memory_types=body.memory_types,
    )

    elapsed_ms = (time.monotonic() - start) * 1000
    memories = [_mem_to_typed_out(mem, score) for mem, score in results]
    return TypedQueryResult(memories=memories, query_time_ms=round(elapsed_ms, 2))


@router.get("/episodic/session/{session_id}", response_model=SessionTimelineResult)
async def get_session_timeline(
    session_id: str,
    namespace: str = Query(default="default", max_length=64),
    include_deprecated: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=1000),
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    """Get episodic memories for a session as an ordered timeline."""
    memories = await MemoryRepository.get_session_timeline(
        db,
        project_id=project_id,
        session_id=session_id,
        namespace=namespace,
        include_deprecated=include_deprecated,
        limit=limit,
    )
    return SessionTimelineResult(
        session_id=session_id,
        memories=[_mem_to_typed_out(m) for m in memories],
        count=len(memories),
    )


@router.get("/semantic/entity/{entity_id}", response_model=EntityFactsResult)
async def get_entity_facts(
    entity_id: str,
    namespace: str = Query(default="default", max_length=64),
    include_deprecated: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=1000),
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    """Get semantic memories (facts) associated with an entity."""
    memories = await MemoryRepository.get_entity_facts(
        db,
        project_id=project_id,
        entity_id=entity_id,
        namespace=namespace,
        include_deprecated=include_deprecated,
        limit=limit,
    )
    return EntityFactsResult(
        entity_id=entity_id,
        memories=[_mem_to_typed_out(m) for m in memories],
        count=len(memories),
    )
