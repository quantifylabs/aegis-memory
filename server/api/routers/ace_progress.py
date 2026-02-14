"""
ACE Session Progress Router (~100 lines)

Handles: /memories/ace/session, /memories/ace/session/{session_id}
"""

from datetime import datetime

from ace_repository import ACERepository
from api.dependencies.auth import check_rate_limit
from api.dependencies.database import get_db, get_read_db
from fastapi import APIRouter, Depends, HTTPException
from observability import OperationNames, record_operation, track_latency
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class SessionProgressCreate(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=64)
    agent_id: str | None = None
    user_id: str | None = None
    namespace: str = "default"


class SessionProgressUpdate(BaseModel):
    completed_items: list[str] | None = None
    in_progress_item: str | None = None
    next_items: list[str] | None = None
    blocked_items: list[dict[str, str]] | None = None
    summary: str | None = None
    last_action: str | None = None
    status: str | None = None
    total_items: int | None = None


class SessionProgressResponse(BaseModel):
    id: str
    session_id: str
    status: str
    completed_count: int
    total_items: int
    progress_percent: float
    completed_items: list[str]
    in_progress_item: str | None
    next_items: list[str]
    blocked_items: list[dict]
    summary: str | None
    last_action: str | None
    updated_at: datetime


def _session_to_response(session) -> SessionProgressResponse:
    completed = session.completed_items or []
    total = session.total_items or len(completed)
    progress = (len(completed) / total * 100) if total > 0 else 0
    return SessionProgressResponse(
        id=session.id, session_id=session.session_id, status=session.status,
        completed_count=len(completed), total_items=total,
        progress_percent=round(progress, 1), completed_items=completed,
        in_progress_item=session.in_progress_item,
        next_items=session.next_items or [], blocked_items=session.blocked_items or [],
        summary=session.summary, last_action=session.last_action, updated_at=session.updated_at,
    )


@router.post("/session", response_model=SessionProgressResponse)
async def create_session(body: SessionProgressCreate, project_id: str = Depends(check_rate_limit), db: AsyncSession = Depends(get_db)):
    """Create a new session for progress tracking."""
    session = await ACERepository.create_session(db, project_id=project_id, session_id=body.session_id, agent_id=body.agent_id, user_id=body.user_id, namespace=body.namespace)
    return _session_to_response(session)


@router.get("/session/{session_id}", response_model=SessionProgressResponse)
async def get_session(session_id: str, project_id: str = Depends(check_rate_limit), db: AsyncSession = Depends(get_read_db)):
    """Get session progress by session_id."""
    session = await ACERepository.get_session(db, session_id, project_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_to_response(session)


@router.patch("/session/{session_id}", response_model=SessionProgressResponse)
async def update_session(session_id: str, body: SessionProgressUpdate, project_id: str = Depends(check_rate_limit), db: AsyncSession = Depends(get_db)):
    """Update session progress."""
    session = await ACERepository.update_session(db, session_id=session_id, project_id=project_id, completed_items=body.completed_items, in_progress_item=body.in_progress_item, next_items=body.next_items, blocked_items=body.blocked_items, summary=body.summary, last_action=body.last_action, status=body.status, total_items=body.total_items)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_to_response(session)
