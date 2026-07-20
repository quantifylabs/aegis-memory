"""
ACE Delta Router (~120 lines)

Handles: /memories/ace/delta
"""

import time
from typing import Any, Literal

from ace_repository import ACERepository
from api.dependencies.auth import AuthContext, check_rate_limit, get_auth_context
from api.dependencies.database import get_db
from config import get_settings
from content_security import ContentSecurityScanner
from embedding_service import get_embedding_service
from event_repository import EventRepository
from fastapi import APIRouter, Depends, HTTPException
from integrity import compute_integrity_hash
from memory_authz import authorize_delete, authorize_write, effective_agent_id
from memory_repository import MemoryRepository
from models import MemoryEventType, MemoryScope, MemoryType
from observability import OperationNames, record_operation, track_latency
from pydantic import BaseModel, Field
from scope_inference import ScopeInference
from sqlalchemy.ext.asyncio import AsyncSession
from trust_levels import resolve_trust_level

router = APIRouter()

_settings = get_settings()
_scanner = ContentSecurityScanner(_settings)


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
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Apply incremental delta updates to memories.

    Every branch here goes through the same gates as ``/memories/*``: the acting agent comes from
    the API key, content is screened before it persists, and the write is authorized against the
    resolved scope. This route previously had none of the three, which mattered most on the ``add``
    branch because reflections default to ``global`` -- the scope every agent in the project reads.
    """
    start = time.monotonic()
    embed_service = get_embedding_service()
    results = []

    enforce_trust = _settings.enable_trust_levels

    for op in body.operations:
        try:
            # Per operation, because an unbound key may legitimately act for different agents
            # across a batch. For a bound key this rejects any op naming a different agent.
            acting_agent_id = effective_agent_id(auth, op.agent_id)

            if op.type == "add":
                if not op.content:
                    results.append(DeltaResultItem(operation="add", success=False, error="Content required"))
                    continue

                # Content provenance derives from the principal: DeltaOperation has no trust_level
                # field, so there is no caller-declared level to cap.
                resolved_trust = resolve_trust_level(None, auth.trust_level, enable_trust_levels=enforce_trust)

                default_scope = MemoryScope.GLOBAL if op.memory_type == MemoryType.REFLECTION.value else None
                requested_scope = op.scope or (default_scope.value if default_scope else None)

                # Screen before anything persists, exactly as the add path does.
                verdict = await _scanner.scan_async(op.content, op.metadata, trust_level=resolved_trust, scope=requested_scope or "agent-private")
                if not verdict.allowed:
                    await EventRepository.create_event(db, memory_id=None, project_id=project_id, namespace=op.namespace, agent_id=acting_agent_id, event_type=MemoryEventType.SECURITY_REJECTED.value, event_payload={"source": "delta_add", "flags": verdict.flags, "detections": [d.detection_type.value for d in verdict.detections]})
                    results.append(DeltaResultItem(operation="add", success=False, error=f"Content rejected by security policy: {verdict.flags}"))
                    continue
                if verdict.flags:
                    await EventRepository.create_event(db, memory_id=None, project_id=project_id, namespace=op.namespace, agent_id=acting_agent_id, event_type=MemoryEventType.SECURITY_FLAGGED.value, event_payload={"source": "delta_add", "flags": verdict.flags})
                content_to_store = verdict.content

                # content_trust_level is what stops inference promoting attacker-controlled content
                # to global on a keyword match. Omitting it (as this route did) disables that cap.
                resolved_scope = ScopeInference.infer_scope(content=content_to_store, explicit_scope=requested_scope, agent_id=acting_agent_id, metadata=op.metadata or {}, content_trust_level=resolved_trust)

                authorize_write(auth, agent_id=acting_agent_id, scope=resolved_scope.value, content_trust_level=resolved_trust, enforce_principal_trust=enforce_trust)

                embedding = await embed_service.embed_single(content_to_store, db)
                integrity_hash = None
                if _settings.enable_integrity_check:
                    integrity_hash = compute_integrity_hash(content_to_store, acting_agent_id, project_id, _settings.get_integrity_key())
                mem = await MemoryRepository.add(db, project_id=project_id, content=content_to_store, embedding=embedding, user_id=op.user_id, agent_id=acting_agent_id, namespace=op.namespace, metadata=op.metadata, ttl_seconds=op.ttl_seconds, scope=resolved_scope.value, memory_type=op.memory_type, integrity_hash=integrity_hash, content_flags=verdict.flags, trust_level=resolved_trust)
                await EventRepository.create_event(db, memory_id=mem.id, project_id=project_id, namespace=mem.namespace, agent_id=mem.agent_id, event_type=MemoryEventType.CREATED.value, event_payload={"source": "delta_add", "memory_type": mem.memory_type})
                results.append(DeltaResultItem(operation="add", success=True, memory_id=mem.id))

            elif op.type == "update":
                if not op.memory_id:
                    results.append(DeltaResultItem(operation="update", success=False, error="memory_id required"))
                    continue
                # Mutating a memory is the write-side equivalent of deleting it: check ownership
                # against the principal, not just project_id.
                target = await MemoryRepository.get_by_id(db, op.memory_id, project_id)
                if target is None:
                    results.append(DeltaResultItem(operation="update", success=False, memory_id=op.memory_id, error="Memory not found"))
                    continue
                authorize_delete(auth, target, enforce_principal_trust=enforce_trust)
                updated = await ACERepository.update_memory_metadata(db, memory_id=op.memory_id, project_id=project_id, metadata_patch=op.metadata_patch)
                results.append(DeltaResultItem(operation="update", success=updated, memory_id=op.memory_id, error=None if updated else "Memory not found"))

            elif op.type == "deprecate":
                if not op.memory_id:
                    results.append(DeltaResultItem(operation="deprecate", success=False, error="memory_id required"))
                    continue
                target = await MemoryRepository.get_by_id(db, op.memory_id, project_id)
                if target is None:
                    results.append(DeltaResultItem(operation="deprecate", success=False, memory_id=op.memory_id, error="Memory not found"))
                    continue
                authorize_delete(auth, target, enforce_principal_trust=enforce_trust)
                deprecated = await ACERepository.deprecate_memory(db, memory_id=op.memory_id, project_id=project_id, deprecated_by=acting_agent_id, superseded_by=op.superseded_by, reason=op.deprecation_reason)
                results.append(DeltaResultItem(operation="deprecate", success=deprecated, memory_id=op.memory_id, error=None if deprecated else "Memory not found"))

        except HTTPException:
            # An authorization denial must never be downgraded into a per-item {success: false}.
            # The blanket ``except Exception`` below would otherwise swallow the 403 and answer 200,
            # making the whole gate look like a routine operation failure to the caller -- and to
            # anyone reading the audit log. Fail the request closed instead.
            raise
        except Exception as e:
            results.append(DeltaResultItem(operation=op.type, success=False, memory_id=op.memory_id, error=str(e)))

    elapsed_ms = (time.monotonic() - start) * 1000
    return DeltaResponse(results=results, total_time_ms=round(elapsed_ms, 2))
