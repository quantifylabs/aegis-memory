"""
Security Router — Admin endpoints for security monitoring, auditing, and configuration.

Endpoints:
  GET  /security/audit          -> Query security events with filters
  GET  /security/flagged        -> List flagged memories pending review
  POST /security/verify/{id}    -> Verify HMAC integrity of a specific memory
  GET  /security/config         -> Current security configuration (signing key redacted)
  POST /security/scan           -> Dry-run content scan without storing

All endpoints require privileged or system trust level.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies.auth import AuthContext, get_auth_context
from api.dependencies.database import get_db, get_read_db
from config import get_settings
from content_security import ContentSecurityScanner, InjectionClassifier
from event_repository import EventRepository
from integrity import verify_integrity
from memory_repository import MemoryRepository
from models import Memory, MemoryEvent, MemoryEventType
from trust_levels import TrustPolicy

router = APIRouter()
settings = get_settings()
scanner = ContentSecurityScanner(settings)

if settings.enable_llm_injection_classifier:
    from aegis_memory.extractors import AnthropicAdapter, OpenAIAdapter
    _sec_api_key = settings.injection_classifier_api_key or settings.openai_api_key
    if settings.injection_classifier_provider == "openai":
        _sec_adapter = OpenAIAdapter(api_key=_sec_api_key, model=settings.injection_classifier_model)
    else:
        _sec_adapter = AnthropicAdapter(api_key=_sec_api_key, model=settings.injection_classifier_model)
    scanner.set_classifier(InjectionClassifier(_sec_adapter, threshold=settings.injection_classifier_confidence_threshold))

SECURITY_EVENT_TYPES = [
    MemoryEventType.SECURITY_FLAGGED.value,
    MemoryEventType.SECURITY_REJECTED.value,
    MemoryEventType.AUTH_FAILED.value,
    MemoryEventType.DELETED.value,
    MemoryEventType.INTEGRITY_FAILED.value,
]


# ---------- Auth Guard ----------

async def require_admin(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
    """Require privileged or system trust level for admin endpoints."""
    if not TrustPolicy.can_admin(auth.trust_level):
        raise HTTPException(status_code=403, detail="Requires privileged or system trust level")
    return auth


# ---------- Request/Response Models ----------

class ScanRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)
    metadata: dict | None = None


class ScanResponse(BaseModel):
    allowed: bool
    action: str
    flags: list[str]
    detections: list[dict]


class VerifyResponse(BaseModel):
    memory_id: str
    integrity_valid: bool
    has_hash: bool
    detail: str


class SecurityConfigResponse(BaseModel):
    content_max_length: int
    metadata_max_depth: int
    metadata_max_keys: int
    content_policy_pii: str
    content_policy_secrets: str
    content_policy_injection: str
    enable_integrity_check: bool
    per_agent_rate_limit_per_minute: int
    per_agent_rate_limit_per_hour: int
    agent_memory_limit: int
    enable_trust_levels: bool
    llm_classifier_enabled: bool = False


class AuditEventOut(BaseModel):
    event_id: str
    event_type: str
    project_id: str
    agent_id: str | None
    memory_id: str | None
    event_payload: dict
    created_at: datetime


class FlaggedMemoryOut(BaseModel):
    id: str
    content: str
    agent_id: str | None
    namespace: str
    content_flags: list[str]
    trust_level: str
    created_at: datetime


# ---------- Endpoints ----------

@router.get("/audit")
async def query_security_audit(
    event_type: str | None = None,
    agent_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_read_db),
):
    """Query security audit events with filters."""
    conditions = [MemoryEvent.project_id == auth.project_id]

    if event_type:
        conditions.append(MemoryEvent.event_type == event_type)
    else:
        conditions.append(MemoryEvent.event_type.in_(SECURITY_EVENT_TYPES))

    if agent_id:
        conditions.append(MemoryEvent.agent_id == agent_id)

    result = await db.execute(
        select(MemoryEvent)
        .where(and_(*conditions))
        .order_by(MemoryEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    events = result.scalars().all()

    return {
        "events": [
            AuditEventOut(
                event_id=e.event_id,
                event_type=e.event_type,
                project_id=e.project_id,
                agent_id=e.agent_id,
                memory_id=e.memory_id,
                event_payload=e.event_payload or {},
                created_at=e.created_at,
            ).model_dump()
            for e in events
        ],
        "count": len(events),
    }


@router.get("/flagged")
async def list_flagged_memories(
    namespace: str = "default",
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_read_db),
):
    """List memories with non-empty content_flags, paginated."""
    conditions = [
        Memory.project_id == auth.project_id,
        Memory.namespace == namespace,
        Memory.content_flags != "[]",
    ]

    result = await db.execute(
        select(Memory)
        .where(and_(*conditions))
        .order_by(Memory.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    memories = result.scalars().all()

    return {
        "memories": [
            FlaggedMemoryOut(
                id=m.id,
                content=m.content,
                agent_id=m.agent_id,
                namespace=m.namespace,
                content_flags=m.content_flags or [],
                trust_level=m.trust_level or "internal",
                created_at=m.created_at,
            ).model_dump()
            for m in memories
        ],
        "count": len(memories),
    }


@router.post("/verify/{memory_id}", response_model=VerifyResponse)
async def verify_memory_integrity(
    memory_id: str,
    auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_read_db),
):
    """Recompute and verify HMAC integrity of a stored memory."""
    mem = await MemoryRepository.get_by_id(db, memory_id, auth.project_id)
    if not mem:
        raise HTTPException(status_code=404, detail=f"Memory not found: {memory_id}")

    if not mem.integrity_hash:
        return VerifyResponse(
            memory_id=memory_id, integrity_valid=False, has_hash=False,
            detail="Legacy memory without integrity hash",
        )

    valid = verify_integrity(mem, settings.get_integrity_key())
    if not valid:
        await EventRepository.log_security_event(
            db, project_id=auth.project_id, memory_id=memory_id,
            event_type=MemoryEventType.INTEGRITY_FAILED.value,
            details={"verified_by": auth.key_id},
        )

    return VerifyResponse(
        memory_id=memory_id, integrity_valid=valid, has_hash=True,
        detail="Integrity verified" if valid else "INTEGRITY MISMATCH — possible tampering",
    )


@router.get("/config", response_model=SecurityConfigResponse)
async def get_security_config(auth: AuthContext = Depends(require_admin)):
    """Return current security configuration (signing key redacted)."""
    return SecurityConfigResponse(
        content_max_length=settings.content_max_length,
        metadata_max_depth=settings.metadata_max_depth,
        metadata_max_keys=settings.metadata_max_keys,
        content_policy_pii=settings.content_policy_pii,
        content_policy_secrets=settings.content_policy_secrets,
        content_policy_injection=settings.content_policy_injection,
        enable_integrity_check=settings.enable_integrity_check,
        per_agent_rate_limit_per_minute=settings.per_agent_rate_limit_per_minute,
        per_agent_rate_limit_per_hour=settings.per_agent_rate_limit_per_hour,
        agent_memory_limit=settings.agent_memory_limit,
        enable_trust_levels=settings.enable_trust_levels,
        llm_classifier_enabled=settings.enable_llm_injection_classifier,
    )


@router.post("/scan", response_model=ScanResponse)
async def scan_content(
    body: ScanRequest,
    auth: AuthContext = Depends(require_admin),
):
    """Dry-run content scan without storing. For client-side pre-validation."""
    verdict = await scanner.scan_async(body.content, body.metadata, trust_level="system", scope="global")
    return ScanResponse(
        allowed=verdict.allowed,
        action=verdict.action.value,
        flags=verdict.flags,
        detections=[
            {"type": d.detection_type.value, "confidence": d.confidence, "pattern": d.matched_pattern}
            for d in verdict.detections
        ],
    )
