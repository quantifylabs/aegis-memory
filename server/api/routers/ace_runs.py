"""
ACE Runs Router

Handles: /memories/ace/run, /memories/ace/run/{run_id}, /memories/ace/run/{run_id}/complete
"""

from datetime import datetime

from ace_repository import ACERepository
from api.dependencies.auth import check_rate_limit
from api.dependencies.database import get_db, get_read_db
from embedding_service import get_embedding_service
from fastapi import APIRouter, Depends, HTTPException
from observability import OperationNames, record_operation, track_latency
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


# ---------- Request/Response Models ----------

class RunCreate(BaseModel):
    """Start tracking an agent run."""
    run_id: str = Field(..., min_length=1, max_length=64)
    agent_id: str | None = Field(default=None, max_length=64)
    task_type: str | None = Field(default=None, max_length=64)
    namespace: str = "default"
    memory_ids_used: list[str] | None = None


class RunComplete(BaseModel):
    """Complete a run with outcome data."""
    success: bool
    evaluation: dict | None = None
    logs: dict | None = None
    auto_vote: bool = True
    auto_reflect: bool = True


class RunResponse(BaseModel):
    run_id: str
    agent_id: str | None
    task_type: str | None
    namespace: str
    status: str
    success: bool | None
    evaluation: dict
    logs: dict
    memory_ids_used: list[str]
    reflection_ids: list[str]
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ---------- Helpers ----------

def _run_to_response(run) -> RunResponse:
    """Convert AceRun model to response."""
    return RunResponse(
        run_id=run.run_id,
        agent_id=run.agent_id,
        task_type=run.task_type,
        namespace=run.namespace,
        status=run.status,
        success=run.success,
        evaluation=run.evaluation or {},
        logs=run.logs or {},
        memory_ids_used=run.memory_ids_used or [],
        reflection_ids=run.reflection_ids or [],
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


# ---------- Routes ----------

@router.post("/run", response_model=RunResponse)
async def create_run(
    body: RunCreate,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    Start tracking an agent run.

    ACE Loop: The Generation phase. Records which memories are being
    used for the current task execution.
    """
    try:
        with track_latency(OperationNames.MEMORY_RUN_CREATE):
            run = await ACERepository.create_run(
                db,
                project_id=project_id,
                run_id=body.run_id,
                agent_id=body.agent_id,
                task_type=body.task_type,
                namespace=body.namespace,
                memory_ids_used=body.memory_ids_used,
            )
        record_operation(OperationNames.MEMORY_RUN_CREATE, "success")
        return _run_to_response(run)
    except Exception:
        record_operation(OperationNames.MEMORY_RUN_CREATE, "error")
        raise


@router.get("/run/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    """Get run details by run_id."""
    try:
        with track_latency(OperationNames.MEMORY_RUN_GET):
            run = await ACERepository.get_run(db, run_id, project_id)

        if not run:
            record_operation(OperationNames.MEMORY_RUN_GET, "error")
            raise HTTPException(status_code=404, detail="Run not found")

        record_operation(OperationNames.MEMORY_RUN_GET, "success")
        return _run_to_response(run)
    except HTTPException:
        raise
    except Exception:
        record_operation(OperationNames.MEMORY_RUN_GET, "error")
        raise


@router.post("/run/{run_id}/complete", response_model=RunResponse)
async def complete_run(
    run_id: str,
    body: RunComplete,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    Complete a run with auto-feedback.

    ACE Loop: The Reflection phase. On completion:
    - Auto-votes memories used (helpful on success, harmful on failure)
    - Auto-creates reflection memories on failure
    - Links run results to playbook entries
    """
    embed_service = get_embedding_service()

    async def embed_fn(content: str) -> list[float]:
        return await embed_service.embed_single(content, db)

    try:
        with track_latency(OperationNames.MEMORY_RUN_COMPLETE):
            run = await ACERepository.complete_run(
                db,
                run_id=run_id,
                project_id=project_id,
                success=body.success,
                evaluation=body.evaluation,
                logs=body.logs,
                auto_vote=body.auto_vote,
                auto_reflect=body.auto_reflect,
                embed_fn=embed_fn,
            )

        if not run:
            record_operation(OperationNames.MEMORY_RUN_COMPLETE, "error")
            raise HTTPException(status_code=404, detail="Run not found")

        record_operation(OperationNames.MEMORY_RUN_COMPLETE, "success")
        return _run_to_response(run)
    except HTTPException:
        raise
    except Exception:
        record_operation(OperationNames.MEMORY_RUN_COMPLETE, "error")
        raise
