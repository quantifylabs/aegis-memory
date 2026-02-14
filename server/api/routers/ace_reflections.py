"""
ACE Reflections + Playbook Router (~80 lines)

Handles: /memories/ace/reflection, /memories/ace/playbook
"""

import time
from datetime import datetime
from typing import Any

from ace_repository import ACERepository
from api.dependencies.auth import check_rate_limit
from api.dependencies.database import get_db
from embedding_service import get_embedding_service
from event_repository import EventRepository
from fastapi import APIRouter, Depends
from models import MemoryEventType, MemoryScope, MemoryType
from observability import OperationNames, record_operation, track_latency
from pydantic import BaseModel, Field
from scope_inference import ScopeInference
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class ReflectionCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)
    agent_id: str = Field(..., min_length=1, max_length=64)
    user_id: str | None = None
    namespace: str = "default"
    source_trajectory_id: str | None = Field(default=None, max_length=64)
    error_pattern: str | None = Field(default=None, max_length=128)
    correct_approach: str | None = Field(default=None, max_length=10_000)
    applicable_contexts: list[str] | None = None
    scope: str | None = None
    metadata: dict[str, Any] | None = None


class ReflectionResponse(BaseModel):
    id: str
    memory_type: str
    scope: str
    effectiveness_score: float


class PlaybookQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=10_000)
    agent_id: str = Field(..., min_length=1, max_length=64)
    namespace: str = "default"
    include_types: list[str] = Field(default=[MemoryType.STRATEGY.value, MemoryType.REFLECTION.value])
    top_k: int = Field(default=20, ge=1, le=100)
    min_effectiveness: float = Field(default=-1.0, ge=-1.0, le=1.0)


class PlaybookEntry(BaseModel):
    id: str
    content: str
    memory_type: str
    effectiveness_score: float
    bullet_helpful: int
    bullet_harmful: int
    error_pattern: str | None
    created_at: datetime


class PlaybookResponse(BaseModel):
    entries: list[PlaybookEntry]
    query_time_ms: float


@router.post("/reflection", response_model=ReflectionResponse)
async def create_reflection(body: ReflectionCreate, project_id: str = Depends(check_rate_limit), db: AsyncSession = Depends(get_db)):
    """Create a reflection memory from trajectory analysis."""
    embed_service = get_embedding_service()
    embedding = await embed_service.embed_single(body.content, db)
    metadata = body.metadata or {}
    if body.correct_approach:
        metadata["correct_approach"] = body.correct_approach
    if body.applicable_contexts:
        metadata["applicable_contexts"] = body.applicable_contexts
    resolved_scope = ScopeInference.infer_scope(content=body.content, explicit_scope=body.scope or MemoryScope.GLOBAL.value, agent_id=body.agent_id, metadata=metadata)
    mem = await ACERepository.create_reflection(db, project_id=project_id, content=body.content, embedding=embedding, agent_id=body.agent_id, user_id=body.user_id, namespace=body.namespace, scope=resolved_scope.value, metadata=metadata, source_trajectory_id=body.source_trajectory_id, error_pattern=body.error_pattern)
    return ReflectionResponse(id=mem.id, memory_type=mem.memory_type, scope=mem.scope, effectiveness_score=mem.get_effectiveness_score())


@router.post("/playbook", response_model=PlaybookResponse)
async def query_playbook(body: PlaybookQueryRequest, project_id: str = Depends(check_rate_limit), db: AsyncSession = Depends(get_db)):
    """Query the playbook for relevant strategies and reflections."""
    start = time.monotonic()
    embed_service = get_embedding_service()
    query_embedding = await embed_service.embed_single(body.query, db)
    results = await ACERepository.query_playbook(db, query_embedding=query_embedding, project_id=project_id, namespace=body.namespace, requesting_agent_id=body.agent_id, include_types=body.include_types, top_k=body.top_k, min_effectiveness=body.min_effectiveness)
    elapsed_ms = (time.monotonic() - start) * 1000
    await EventRepository.create_event(db, project_id=project_id, namespace=body.namespace, agent_id=body.agent_id, event_type=MemoryEventType.QUERIED.value, event_payload={"source": "playbook", "query": body.query, "result_count": len(results)})
    entries = [PlaybookEntry(id=mem.id, content=mem.content, memory_type=mem.memory_type, effectiveness_score=mem.get_effectiveness_score(), bullet_helpful=mem.bullet_helpful, bullet_harmful=mem.bullet_harmful, error_pattern=mem.error_pattern, created_at=mem.created_at) for mem, score in results]
    return PlaybookResponse(entries=entries, query_time_ms=round(elapsed_ms, 2))
