"""
ACE Curation Router

Handles: /memories/ace/playbook/agent, /memories/ace/curate
"""

import time
from datetime import datetime

from ace_repository import ACERepository
from api.dependencies.auth import check_rate_limit
from api.dependencies.database import get_db
from embedding_service import get_embedding_service
from event_repository import EventRepository
from fastapi import APIRouter, Depends
from models import MemoryEventType
from observability import OperationNames, record_operation, track_latency
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


# ---------- Request/Response Models ----------

class AgentPlaybookRequest(BaseModel):
    """Query playbook for a specific agent."""
    query: str = Field(..., min_length=1, max_length=10_000)
    agent_id: str = Field(..., min_length=1, max_length=64)
    task_type: str | None = Field(default=None, max_length=64)
    namespace: str = "default"
    top_k: int = Field(default=20, ge=1, le=100)
    min_effectiveness: float = Field(default=-1.0, ge=-1.0, le=1.0)


class CurateRequest(BaseModel):
    """Trigger a curation cycle."""
    namespace: str = "default"
    agent_id: str | None = Field(default=None, max_length=64)
    top_k: int = Field(default=10, ge=1, le=100)
    min_effectiveness_threshold: float = Field(default=-0.3, ge=-1.0, le=1.0)


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


class CurationEntryResponse(BaseModel):
    id: str
    content: str
    memory_type: str
    effectiveness_score: float
    bullet_helpful: int
    bullet_harmful: int
    total_votes: int


class ConsolidationCandidate(BaseModel):
    memory_id_a: str
    memory_id_b: str
    content_a: str
    content_b: str
    reason: str


class CurationResponse(BaseModel):
    promoted: list[CurationEntryResponse]
    flagged: list[CurationEntryResponse]
    consolidation_candidates: list[ConsolidationCandidate]


# ---------- Helpers ----------

async def _emit_event(
    db: AsyncSession,
    *,
    project_id: str,
    namespace: str,
    event_type: str,
    memory_id: str | None = None,
    agent_id: str | None = None,
    payload: dict | None = None,
) -> None:
    await EventRepository.create_event(
        db,
        memory_id=memory_id,
        project_id=project_id,
        namespace=namespace,
        agent_id=agent_id,
        event_type=event_type,
        event_payload=payload or {},
    )


# ---------- Routes ----------

@router.post("/playbook/agent", response_model=PlaybookResponse)
async def get_playbook_for_agent(
    body: AgentPlaybookRequest,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    Get playbook entries filtered by agent_id and optional task_type.

    ACE Loop: Before starting a task, query agent-specific strategies
    and reflections that have been validated by past runs.
    """
    start = time.monotonic()
    embed_service = get_embedding_service()

    query_embedding = await embed_service.embed_single(body.query, db)

    results = await ACERepository.get_playbook_for_agent(
        db,
        query_embedding=query_embedding,
        project_id=project_id,
        agent_id=body.agent_id,
        namespace=body.namespace,
        task_type=body.task_type,
        top_k=body.top_k,
        min_effectiveness=body.min_effectiveness,
    )

    elapsed_ms = (time.monotonic() - start) * 1000

    await _emit_event(
        db,
        project_id=project_id,
        namespace=body.namespace,
        agent_id=body.agent_id,
        event_type=MemoryEventType.QUERIED.value,
        payload={
            "source": "playbook_agent",
            "query": body.query,
            "task_type": body.task_type,
            "result_count": len(results),
        },
    )

    entries = [
        PlaybookEntry(
            id=mem.id,
            content=mem.content,
            memory_type=mem.memory_type,
            effectiveness_score=mem.get_effectiveness_score(),
            bullet_helpful=mem.bullet_helpful,
            bullet_harmful=mem.bullet_harmful,
            error_pattern=mem.error_pattern,
            created_at=mem.created_at,
        )
        for mem, score in results
    ]

    return PlaybookResponse(
        entries=entries,
        query_time_ms=round(elapsed_ms, 2),
    )


@router.post("/curate", response_model=CurationResponse)
async def curate(
    body: CurateRequest,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger a curation cycle.

    ACE Loop: The Curation phase. Identifies:
    - Promoted: high-effectiveness entries validated by runs
    - Flagged: low-effectiveness entries for deprecation
    - Consolidation candidates: similar entries that could be merged
    """
    try:
        with track_latency(OperationNames.MEMORY_CURATE):
            result = await ACERepository.curate(
                db,
                project_id=project_id,
                namespace=body.namespace,
                agent_id=body.agent_id,
                top_k=body.top_k,
                min_effectiveness_threshold=body.min_effectiveness_threshold,
            )

        record_operation(OperationNames.MEMORY_CURATE, "success")

        return CurationResponse(
            promoted=[CurationEntryResponse(**e) for e in result["promoted"]],
            flagged=[CurationEntryResponse(**e) for e in result["flagged"]],
            consolidation_candidates=[
                ConsolidationCandidate(**c) for c in result["consolidation_candidates"]
            ],
        )
    except Exception:
        record_operation(OperationNames.MEMORY_CURATE, "error")
        raise
