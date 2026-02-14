"""
Memory CRUD + Export Router (~250 lines)

Handles: /memories/add, /add_batch, /query, /query_cross_agent, /{id}, /export
"""

import json
import time
from datetime import datetime
from typing import Any

from api.dependencies.auth import check_rate_limit
from api.dependencies.database import get_db, get_read_db
from embedding_service import content_hash, get_embedding_service
from event_repository import EventRepository
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from memory_repository import MemoryRepository
from models import Memory, MemoryEventType, MemoryScope
from observability import OperationNames, record_memory_stored_scope, record_operation, record_query_execution, track_latency
from pydantic import BaseModel, Field, field_validator
from scope_inference import ScopeInference
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


# ---------- Request/Response Models ----------

class MemoryCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)
    user_id: str | None = Field(default=None, max_length=64)
    agent_id: str | None = Field(default=None, max_length=64)
    namespace: str = Field(default="default", max_length=64)
    metadata: dict[str, Any] | None = None
    ttl_seconds: int | None = Field(default=None, ge=1, le=31536000)
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
    task_id: str | None = Field(default=None, max_length=128)
    selected_memory_ids: list[str] | None = None
    scope: str | None = None
    namespace: str = "default"
    top_k: int = Field(default=10, ge=1, le=100)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    memory_types: list[str] | None = None


class CrossAgentQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=10_000)
    requesting_agent_id: str = Field(..., min_length=1, max_length=64)
    target_agent_ids: list[str] | None = None
    user_id: str | None = None
    task_id: str | None = Field(default=None, max_length=128)
    selected_memory_ids: list[str] | None = None
    scope: str | None = None
    namespace: str = "default"
    top_k: int = Field(default=10, ge=1, le=100)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class MemoryOut(BaseModel):
    id: str
    content: str
    memory_type: str = "standard"
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
    retrieval_event_id: str | None = None


class ExportRequest(BaseModel):
    namespace: str | None = None
    agent_id: str | None = None
    format: str = Field(default="jsonl", pattern="^(jsonl|json)$")
    include_embeddings: bool = False
    limit: int | None = Field(default=None, ge=1, le=100000)


def _mem_to_out(mem: Memory, score: float | None = None) -> MemoryOut:
    return MemoryOut(
        id=mem.id, content=mem.content,
        memory_type=mem.memory_type or "standard",
        user_id=mem.user_id,
        agent_id=mem.agent_id, namespace=mem.namespace,
        metadata=mem.metadata_json or {}, created_at=mem.created_at,
        scope=mem.scope, shared_with_agents=mem.shared_with_agents or [],
        derived_from_agents=mem.derived_from_agents or [],
        coordination_metadata=mem.coordination_metadata or {},
        session_id=mem.session_id,
        entity_id=mem.entity_id,
        sequence_number=mem.sequence_number,
        score=score,
    )


async def _emit(db, *, project_id, namespace, event_type, memory_id=None, agent_id=None, payload=None, task_id=None, selected_memory_ids=None):
    return await EventRepository.create_event(
        db, memory_id=memory_id, project_id=project_id, namespace=namespace,
        agent_id=agent_id, event_type=event_type, event_payload=payload or {},
        task_id=task_id, selected_memory_ids=selected_memory_ids,
    )


# ---------- Endpoints ----------

@router.post("/add", response_model=AddResult)
async def add_memory(body: MemoryCreate, project_id: str = Depends(check_rate_limit), db: AsyncSession = Depends(get_db)):
    """Add a single memory with automatic scope inference and deduplication."""
    try:
        with track_latency(OperationNames.MEMORY_ADD):
            embed_service = get_embedding_service()
            hash_val = content_hash(body.content)
            existing = await MemoryRepository.find_duplicates(db, content_hash=hash_val, project_id=project_id, namespace=body.namespace, user_id=body.user_id, agent_id=body.agent_id)
            if existing:
                record_operation(OperationNames.MEMORY_ADD, "success")
                return AddResult(id=existing.id, deduped_from=existing.id)
            embedding = await embed_service.embed_single(body.content, db)
            resolved_scope = ScopeInference.infer_scope(content=body.content, explicit_scope=body.scope, agent_id=body.agent_id, metadata=body.metadata or {})
            mem = await MemoryRepository.add(db, project_id=project_id, content=body.content, embedding=embedding, user_id=body.user_id, agent_id=body.agent_id, namespace=body.namespace, metadata=body.metadata, ttl_seconds=body.ttl_seconds, scope=resolved_scope.value, shared_with_agents=body.shared_with_agents, derived_from_agents=body.derived_from_agents, coordination_metadata=body.coordination_metadata)
            record_memory_stored_scope(resolved_scope.value)
            await _emit(db, project_id=project_id, memory_id=mem.id, namespace=mem.namespace, agent_id=mem.agent_id, event_type=MemoryEventType.CREATED.value, payload={"source": "add"})
            record_operation(OperationNames.MEMORY_ADD, "success")
            return AddResult(id=mem.id, inferred_scope=resolved_scope.value if body.scope is None else None)
    except Exception:
        record_operation(OperationNames.MEMORY_ADD, "error")
        raise


@router.post("/add_batch", response_model=AddBatchResult)
async def add_memory_batch(body: MemoryCreateBatch, project_id: str = Depends(check_rate_limit), db: AsyncSession = Depends(get_db)):
    """Add multiple memories efficiently with batched embedding."""
    start = time.monotonic()
    embed_service = get_embedding_service()
    texts = [item.content for item in body.items]
    embeddings = await embed_service.embed_batch(texts, db)
    results = []
    to_insert = []
    for i, item in enumerate(body.items):
        hash_val = content_hash(item.content)
        existing = await MemoryRepository.find_duplicates(db, content_hash=hash_val, project_id=project_id, namespace=item.namespace, user_id=item.user_id, agent_id=item.agent_id)
        if existing:
            results.append(AddResult(id=existing.id, deduped_from=existing.id))
            continue
        resolved_scope = ScopeInference.infer_scope(content=item.content, explicit_scope=item.scope, agent_id=item.agent_id, metadata=item.metadata or {})
        to_insert.append({"project_id": project_id, "content": item.content, "embedding": embeddings[i], "user_id": item.user_id, "agent_id": item.agent_id, "namespace": item.namespace, "metadata": item.metadata, "ttl_seconds": item.ttl_seconds, "scope": resolved_scope.value, "shared_with_agents": item.shared_with_agents, "derived_from_agents": item.derived_from_agents, "coordination_metadata": item.coordination_metadata})
        results.append(None)
    if to_insert:
        memories = await MemoryRepository.add_batch(db, to_insert)
        for item in to_insert:
            record_memory_stored_scope(item["scope"])
        for mem in memories:
            await _emit(db, project_id=project_id, memory_id=mem.id, namespace=mem.namespace, agent_id=mem.agent_id, event_type=MemoryEventType.CREATED.value, payload={"source": "add_batch"})
        mem_iter = iter(memories)
        for i in range(len(results)):
            if results[i] is None:
                mem = next(mem_iter)
                results[i] = AddResult(id=mem.id)
    elapsed_ms = (time.monotonic() - start) * 1000
    stats = embed_service.get_stats()
    return AddBatchResult(results=results, embeddings_cached=stats["cache_hits"], total_time_ms=round(elapsed_ms, 2))


@router.post("/query", response_model=QueryResult)
async def query_memories(body: MemoryQuery, project_id: str = Depends(check_rate_limit), db: AsyncSession = Depends(get_db)):
    """Semantic search over memories."""
    start = time.monotonic()
    try:
        with track_latency(OperationNames.MEMORY_QUERY):
            embed_service = get_embedding_service()
            query_embedding = await embed_service.embed_single(body.query, db)
            results, query_meta = await MemoryRepository.semantic_search(db, query_embedding=query_embedding, project_id=project_id, namespace=body.namespace, user_id=body.user_id, agent_id=body.agent_id, requesting_agent_id=body.agent_id, top_k=body.top_k, min_score=body.min_score, requested_scope=body.scope, memory_types=body.memory_types)
        elapsed_ms = (time.monotonic() - start) * 1000
        memories = [_mem_to_out(mem, score) for mem, score in results]
        retrieved_ids = [mem.id for mem, _ in results]
        event = await _emit(db, project_id=project_id, namespace=body.namespace, agent_id=body.agent_id, event_type=MemoryEventType.QUERIED.value, payload={"query": body.query, "result_count": len(memories), "top_k": body.top_k}, task_id=body.task_id, selected_memory_ids=body.selected_memory_ids or retrieved_ids)
        record_operation(OperationNames.MEMORY_QUERY, "success")
        return QueryResult(memories=memories, query_time_ms=round(elapsed_ms, 2), retrieval_event_id=event.event_id)
    except Exception:
        record_operation(OperationNames.MEMORY_QUERY, "error")
        raise


@router.post("/query_cross_agent", response_model=QueryResult)
async def query_cross_agent(body: CrossAgentQuery, project_id: str = Depends(check_rate_limit), db: AsyncSession = Depends(get_db)):
    """Cross-agent semantic search with scope-aware access control."""
    start = time.monotonic()
    embed_service = get_embedding_service()
    query_embedding = await embed_service.embed_single(body.query, db)
    results, query_meta = await MemoryRepository.semantic_search(db, query_embedding=query_embedding, project_id=project_id, namespace=body.namespace, user_id=body.user_id, requesting_agent_id=body.requesting_agent_id, target_agent_ids=body.target_agent_ids, top_k=body.top_k, min_score=body.min_score, requested_scope=body.scope)
    elapsed_ms = (time.monotonic() - start) * 1000
    memories = [_mem_to_out(mem, score) for mem, score in results]
    event = await _emit(db, project_id=project_id, namespace=body.namespace, agent_id=body.requesting_agent_id, event_type=MemoryEventType.QUERIED.value, payload={"source": "query_cross_agent", "query": body.query, "result_count": len(memories), "top_k": body.top_k, "target_agent_ids": body.target_agent_ids or []}, task_id=body.task_id, selected_memory_ids=body.selected_memory_ids or [mem.id for mem, _ in results])
    return QueryResult(memories=memories, query_time_ms=round(elapsed_ms, 2), retrieval_event_id=event.event_id)


@router.get("/{memory_id}", response_model=MemoryOut)
async def get_memory(memory_id: str, project_id: str = Depends(check_rate_limit), db: AsyncSession = Depends(get_read_db)):
    """Get a single memory by ID."""
    mem = await MemoryRepository.get_by_id(db, memory_id, project_id)
    if not mem:
        raise HTTPException(status_code=404, detail=f"Memory not found: {memory_id}")
    return _mem_to_out(mem)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(memory_id: str, project_id: str = Depends(check_rate_limit), db: AsyncSession = Depends(get_db)):
    """Delete a memory by ID."""
    deleted = await MemoryRepository.delete(db, memory_id, project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Memory not found: {memory_id}")


@router.post("/export")
async def export_memories(body: ExportRequest, project_id: str = Depends(check_rate_limit), db: AsyncSession = Depends(get_read_db)):
    """Export memories for backup or migration."""
    conditions = [Memory.project_id == project_id]
    if body.namespace:
        conditions.append(Memory.namespace == body.namespace)
    if body.agent_id:
        conditions.append(Memory.agent_id == body.agent_id)
    base_stmt = select(Memory).where(and_(*conditions)).order_by(Memory.created_at, Memory.id)
    namespaces, agents = set(), set()

    def serialize(mem):
        namespaces.add(mem.namespace)
        if mem.agent_id:
            agents.add(mem.agent_id)
        data = {"id": mem.id, "content": mem.content, "user_id": mem.user_id, "agent_id": mem.agent_id, "namespace": mem.namespace, "scope": mem.scope, "metadata": mem.metadata_json or {}, "memory_type": mem.memory_type, "created_at": mem.created_at.isoformat(), "updated_at": mem.updated_at.isoformat() if mem.updated_at else None, "bullet_helpful": mem.bullet_helpful, "bullet_harmful": mem.bullet_harmful}
        if body.include_embeddings:
            data["embedding"] = list(mem.embedding) if mem.embedding else None
        return data

    async def iter_memories():
        fetched, cursor_created_at, cursor_id = 0, None, None
        while True:
            remaining = None if body.limit is None else body.limit - fetched
            if remaining is not None and remaining <= 0:
                break
            stmt = base_stmt
            if cursor_created_at is not None and cursor_id is not None:
                stmt = stmt.where(or_(Memory.created_at > cursor_created_at, and_(Memory.created_at == cursor_created_at, Memory.id > cursor_id)))
            batch_limit = 1000 if remaining is None else min(1000, remaining)
            stmt = stmt.limit(batch_limit)
            result = await db.execute(stmt)
            batch = result.scalars().all()
            if not batch:
                break
            for mem in batch:
                yield mem
            fetched += len(batch)
            cursor_created_at, cursor_id = batch[-1].created_at, batch[-1].id
            if len(batch) < batch_limit:
                break

    if body.format == "jsonl":
        total = (await db.execute(select(func.count()).where(and_(*conditions)))).scalar_one()
        if body.limit:
            total = min(total, body.limit)

        async def generate():
            async for mem in iter_memories():
                yield json.dumps(serialize(mem)) + "\n"

        return StreamingResponse(generate(), media_type="application/x-ndjson", headers={"Content-Disposition": f"attachment; filename=aegis_export_{project_id}.jsonl", "X-Export-Total": str(total)})
    else:
        exported = [serialize(mem) async for mem in iter_memories()]
        return {"memories": exported, "stats": {"total_exported": len(exported), "format": body.format, "namespaces": list(namespaces), "agents": list(agents)}}
