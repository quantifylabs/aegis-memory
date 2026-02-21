"""
Interaction Events Router (v1.9.11)

Lightweight multi-agent collaboration history with causal chain support.
5 endpoints: create, session timeline, agent history, search, event+chain.

Route ordering note: /{event_id} is declared last to prevent FastAPI from
matching /session/... or /agent/... as event IDs.
"""

import time
from datetime import datetime
from typing import Any

from embedding_service import get_embedding_service
from fastapi import APIRouter, Depends, HTTPException, Query
from interaction_repository import InteractionRepository
from models import InteractionEvent
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies.auth import check_rate_limit
from api.dependencies.database import get_db, get_read_db

router = APIRouter()


# ---------- Pydantic Models ----------


class InteractionEventCreate(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=64)
    content: str = Field(..., min_length=1, max_length=100_000)
    agent_id: str | None = Field(default=None, max_length=64)
    tool_calls: list[dict[str, Any]] | None = None
    parent_event_id: str | None = Field(default=None, max_length=32)
    namespace: str = Field(default="default", max_length=64)
    extra_metadata: dict[str, Any] | None = None
    embed: bool = Field(default=False, description="Generate and store an embedding for semantic search")


class InteractionSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=10_000)
    namespace: str = Field(default="default", max_length=64)
    session_id: str | None = None
    agent_id: str | None = None
    top_k: int = Field(default=10, ge=1, le=100)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class InteractionEventOut(BaseModel):
    event_id: str
    project_id: str
    session_id: str
    agent_id: str | None
    content: str | None
    timestamp: datetime
    tool_calls: list[Any]
    parent_event_id: str | None
    namespace: str
    extra_metadata: dict[str, Any] | None
    has_embedding: bool

    class Config:
        from_attributes = True


class InteractionEventCreateResult(BaseModel):
    event_id: str
    session_id: str
    namespace: str
    has_embedding: bool


class SessionTimelineResult(BaseModel):
    session_id: str
    namespace: str
    events: list[InteractionEventOut]
    count: int


class AgentInteractionsResult(BaseModel):
    agent_id: str
    namespace: str
    events: list[InteractionEventOut]
    count: int


class InteractionSearchResultItem(BaseModel):
    event: InteractionEventOut
    score: float


class InteractionSearchResult(BaseModel):
    results: list[InteractionSearchResultItem]
    query_time_ms: float


class EventWithChainResult(BaseModel):
    event: InteractionEventOut
    chain: list[InteractionEventOut]
    chain_depth: int


# ---------- Helpers ----------


def _event_to_out(event: InteractionEvent) -> InteractionEventOut:
    return InteractionEventOut(
        event_id=event.event_id,
        project_id=event.project_id,
        session_id=event.session_id,
        agent_id=event.agent_id,
        content=event.content,
        timestamp=event.timestamp,
        tool_calls=event.tool_calls or [],
        parent_event_id=event.parent_event_id,
        namespace=event.namespace,
        extra_metadata=event.extra_metadata,
        has_embedding=event.embedding is not None,
    )


# ---------- Endpoints ----------


@router.post("/", response_model=InteractionEventCreateResult, status_code=201)
async def create_interaction_event(
    body: InteractionEventCreate,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    Record an interaction event.

    Set embed=True to generate a vector embedding for later semantic search.
    Causal chains are built by setting parent_event_id to a prior event's ID.
    """
    embedding = None
    if body.embed:
        embed_service = get_embedding_service()
        embedding = await embed_service.embed_single(body.content, db)

    event = await InteractionRepository.create_event(
        db,
        project_id=project_id,
        session_id=body.session_id,
        content=body.content,
        agent_id=body.agent_id,
        tool_calls=body.tool_calls,
        parent_event_id=body.parent_event_id,
        namespace=body.namespace,
        extra_metadata=body.extra_metadata,
        embedding=embedding,
    )

    return InteractionEventCreateResult(
        event_id=event.event_id,
        session_id=event.session_id,
        namespace=event.namespace,
        has_embedding=event.embedding is not None,
    )


@router.get("/session/{session_id}", response_model=SessionTimelineResult)
async def get_session_timeline(
    session_id: str,
    namespace: str = Query(default="default", max_length=64),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    """Get interaction events for a session ordered by timestamp ASC."""
    events = await InteractionRepository.get_session_timeline(
        db,
        project_id=project_id,
        session_id=session_id,
        namespace=namespace,
        limit=limit,
        offset=offset,
    )
    return SessionTimelineResult(
        session_id=session_id,
        namespace=namespace,
        events=[_event_to_out(e) for e in events],
        count=len(events),
    )


@router.get("/agent/{agent_id}", response_model=AgentInteractionsResult)
async def get_agent_interactions(
    agent_id: str,
    namespace: str = Query(default="default", max_length=64),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    """Get interaction events for an agent ordered by timestamp DESC (most recent first)."""
    events = await InteractionRepository.get_agent_interactions(
        db,
        project_id=project_id,
        agent_id=agent_id,
        namespace=namespace,
        limit=limit,
        offset=offset,
    )
    return AgentInteractionsResult(
        agent_id=agent_id,
        namespace=namespace,
        events=[_event_to_out(e) for e in events],
        count=len(events),
    )


@router.post("/search", response_model=InteractionSearchResult)
async def search_interactions(
    body: InteractionSearchRequest,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    Semantic search over interaction events.

    Only events created with embed=True are searchable.
    Returns events sorted by cosine similarity (highest first).
    """
    start = time.monotonic()
    embed_service = get_embedding_service()
    query_embedding = await embed_service.embed_single(body.query, db)

    results = await InteractionRepository.search(
        db,
        project_id=project_id,
        query_embedding=query_embedding,
        namespace=body.namespace,
        session_id=body.session_id,
        agent_id=body.agent_id,
        top_k=body.top_k,
        min_score=body.min_score,
    )

    elapsed_ms = (time.monotonic() - start) * 1000
    return InteractionSearchResult(
        results=[
            InteractionSearchResultItem(event=_event_to_out(event), score=score)
            for event, score in results
        ],
        query_time_ms=round(elapsed_ms, 2),
    )


# NOTE: /{event_id} must be declared after /session/{session_id} and /agent/{agent_id}
# to prevent FastAPI from matching those path segments as event IDs.
@router.get("/{event_id}", response_model=EventWithChainResult)
async def get_event_with_chain(
    event_id: str,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    """
    Get an interaction event plus its full causal chain.

    The chain is ordered root → leaf (oldest ancestor first).
    Returns 404 if the event does not exist in this project.
    """
    event = await InteractionRepository.get_event(
        db,
        event_id=event_id,
        project_id=project_id,
    )
    if event is None:
        raise HTTPException(status_code=404, detail=f"Interaction event {event_id!r} not found")

    chain = await InteractionRepository.get_with_chain(
        db,
        event_id=event_id,
        project_id=project_id,
    )

    return EventWithChainResult(
        event=_event_to_out(event),
        chain=[_event_to_out(e) for e in chain],
        chain_depth=len(chain),
    )
