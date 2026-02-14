"""
ACE Delta Router (~120 lines)

Handles: /memories/ace/delta
"""

import time
from typing import Any, Literal

from ace_repository import ACERepository
from api.dependencies.auth import check_rate_limit
from api.dependencies.database import get_db
from embedding_service import get_embedding_service
from event_repository import EventRepository
from fastapi import APIRouter, Depends
from memory_repository import MemoryRepository
from models import MemoryEventType, MemoryScope, MemoryType
from observability import OperationNames, record_operation, track_latency
from pydantic import BaseModel, Field
from scope_inference import ScopeInference
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class DeltaOperation(BaseModel):
    type: Literal["add", "update", "deprecate"]
    content: str | None = Field(default=None, max_length=100_000)
    memory_type: str | None = Field(default=MemoryType.STANDARD.value)
    agent_id: str | None = None
    user_id: str | None = None
    namespace: str = "default"
    scope: str | None = None
    metadata: dict[str, Any] | None = None
    ttl_seconds: int | None = None
    memory_id: str | None = None
    metadata_patch: dict[str, Any] | None = None
    superseded_by: str | None = None
    deprecation_reason: str | None = None


class DeltaRequest(BaseModel):
    operations: list[DeltaOperation] = Field(..., min_length=1, max_length=100)


class DeltaResultItem(BaseModel):
    operation: str
    success: bool
    memory_id: str | None = None
    error: str | None = None


class DeltaResponse(BaseModel):
    results: list[DeltaResultItem]
    total_time_ms: float


@router.post("/delta", response_model=DeltaResponse)
async def apply_delta(
    body: DeltaRequest,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """Apply incremental delta updates to memories."""
    start = time.monotonic()
    embed_service = get_embedding_service()
    results = []

    for op in body.operations:
        try:
            if op.type == "add":
                if not op.content:
                    results.append(DeltaResultItem(operation="add", success=False, error="Content required"))
                    continue
                embedding = await embed_service.embed_single(op.content, db)
                default_scope = MemoryScope.GLOBAL if op.memory_type == MemoryType.REFLECTION.value else None
                resolved_scope = ScopeInference.infer_scope(content=op.content, explicit_scope=op.scope or (default_scope.value if default_scope else None), agent_id=op.agent_id, metadata=op.metadata or {})
                mem = await MemoryRepository.add(db, project_id=project_id, content=op.content, embedding=embedding, user_id=op.user_id, agent_id=op.agent_id, namespace=op.namespace, metadata=op.metadata, ttl_seconds=op.ttl_seconds, scope=resolved_scope.value, memory_type=op.memory_type)
                await EventRepository.create_event(db, memory_id=mem.id, project_id=project_id, namespace=mem.namespace, agent_id=mem.agent_id, event_type=MemoryEventType.CREATED.value, event_payload={"source": "delta_add", "memory_type": mem.memory_type})
                results.append(DeltaResultItem(operation="add", success=True, memory_id=mem.id))

            elif op.type == "update":
                if not op.memory_id:
                    results.append(DeltaResultItem(operation="update", success=False, error="memory_id required"))
                    continue
                updated = await ACERepository.update_memory_metadata(db, memory_id=op.memory_id, project_id=project_id, metadata_patch=op.metadata_patch)
                results.append(DeltaResultItem(operation="update", success=updated, memory_id=op.memory_id, error=None if updated else "Memory not found"))

            elif op.type == "deprecate":
                if not op.memory_id:
                    results.append(DeltaResultItem(operation="deprecate", success=False, error="memory_id required"))
                    continue
                deprecated = await ACERepository.deprecate_memory(db, memory_id=op.memory_id, project_id=project_id, deprecated_by=op.agent_id, superseded_by=op.superseded_by, reason=op.deprecation_reason)
                results.append(DeltaResultItem(operation="deprecate", success=deprecated, memory_id=op.memory_id, error=None if deprecated else "Memory not found"))

        except Exception as e:
            results.append(DeltaResultItem(operation=op.type, success=False, memory_id=op.memory_id, error=str(e)))

    elapsed_ms = (time.monotonic() - start) * 1000
    return DeltaResponse(results=results, total_time_ms=round(elapsed_ms, 2))
