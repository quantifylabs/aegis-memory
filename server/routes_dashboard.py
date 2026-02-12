from datetime import datetime, timedelta
from typing import Any

from database import get_read_db
from event_repository import EventRepository
from fastapi import APIRouter, Depends, Query
from models import FeatureTracker, Memory, MemoryEvent, MemoryType, SessionProgress
from observability import get_query_analytics
from pydantic import BaseModel
from routes import check_rate_limit
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/memories/ace/dashboard", tags=["dashboard"])


class DashboardStats(BaseModel):
    total_memories: int
    total_reflections: int
    total_strategies: int
    total_features: int
    recent_activity_count: int
    top_agents: list[dict]


class ActivityItem(BaseModel):
    id: str
    memory_type: str
    content_preview: str
    agent_id: str | None
    effectiveness_score: float
    bullet_helpful: int
    bullet_harmful: int
    created_at: datetime
    error_pattern: str | None


class ActivityFeed(BaseModel):
    items: list[ActivityItem]


class QueryIntentStat(BaseModel):
    intent: str
    count: int


class HitRateBucket(BaseModel):
    bucket_start: datetime
    queries: int
    hits: int
    hit_rate: float


class ScopeUsageStat(BaseModel):
    scope: str
    count: int


class AgentRetrievalShare(BaseModel):
    agent_id: str
    retrievals: int
    share: float


class DashboardAnalytics(BaseModel):
    window_minutes: int
    sample_size: int
    top_query_intents: list[QueryIntentStat]
    hit_rate_trend: list[HitRateBucket]
    scope_usage_breakdown: list[ScopeUsageStat]
    per_agent_retrieval_share: list[AgentRetrievalShare]


class TimelineEvent(BaseModel):
    event_id: str
    memory_id: str | None
    project_id: str
    namespace: str
    agent_id: str | None
    event_type: str
    event_payload: dict[str, Any]
    created_at: datetime


class TimelineResponse(BaseModel):
    items: list[TimelineEvent]
    limit: int
    offset: int


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    namespace: str = "default",
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    """Aggregate stats for the 'The Brain' view."""

    total_memories = await db.scalar(
        select(func.count(Memory.id)).where(Memory.project_id == project_id)
    )

    total_reflections = await db.scalar(
        select(func.count(Memory.id)).where(
            Memory.project_id == project_id,
            Memory.memory_type == MemoryType.REFLECTION.value,
        )
    )

    total_strategies = await db.scalar(
        select(func.count(Memory.id)).where(
            Memory.project_id == project_id,
            Memory.memory_type == MemoryType.STRATEGY.value,
        )
    )

    total_features = await db.scalar(
        select(func.count(FeatureTracker.id)).where(FeatureTracker.project_id == project_id)
    )

    yesterday = datetime.utcnow() - timedelta(hours=24)
    recent_activity = await db.scalar(
        select(func.count(Memory.id)).where(
            Memory.project_id == project_id,
            Memory.created_at >= yesterday,
        )
    )

    top_agents_result = await db.execute(
        select(Memory.agent_id, func.count(Memory.id).label("count"))
        .where(Memory.project_id == project_id, Memory.agent_id.is_not(None))
        .group_by(Memory.agent_id)
        .order_by(desc("count"))
        .limit(5)
    )

    top_agents = [
        {"agent_id": row.agent_id, "memory_count": row.count}
        for row in top_agents_result
    ]

    _ = namespace
    return DashboardStats(
        total_memories=total_memories or 0,
        total_reflections=total_reflections or 0,
        total_strategies=total_strategies or 0,
        total_features=total_features or 0,
        recent_activity_count=recent_activity or 0,
        top_agents=top_agents,
    )


@router.get("/activity", response_model=ActivityFeed)
async def get_activity_feed(
    namespace: str = "default",
    limit: int = 50,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    """Get recent timeline for 'Live Feed'."""
    query = (
        select(Memory)
        .where(Memory.project_id == project_id)
        .order_by(desc(Memory.created_at))
        .limit(limit)
    )

    result = await db.execute(query)
    memories = result.scalars().all()

    items = []
    for m in memories:
        items.append(
            ActivityItem(
                id=m.id,
                memory_type=m.memory_type,
                content_preview=m.content[:200] + "..." if len(m.content) > 200 else m.content,
                agent_id=m.agent_id,
                effectiveness_score=m.get_effectiveness_score(),
                bullet_helpful=m.bullet_helpful,
                bullet_harmful=m.bullet_harmful,
                created_at=m.created_at,
                error_pattern=m.error_pattern,
            )
        )

    _ = namespace
    return ActivityFeed(items=items)


@router.get("/timeline", response_model=TimelineResponse)
async def get_project_timeline(
    namespace: str | None = None,
    event_types: list[str] | None = Query(default=None),
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    events = await EventRepository.get_project_timeline(
        db,
        project_id=project_id,
        namespace=namespace,
        event_types=event_types,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )
    return TimelineResponse(
        items=[_event_to_response(e) for e in events],
        limit=limit,
        offset=offset,
    )


@router.get("/timeline/memory/{memory_id}", response_model=TimelineResponse)
async def get_memory_timeline(
    memory_id: str,
    event_types: list[str] | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    events = await EventRepository.get_memory_timeline(
        db,
        project_id=project_id,
        memory_id=memory_id,
        event_types=event_types,
        limit=limit,
        offset=offset,
    )
    return TimelineResponse(
        items=[_event_to_response(e) for e in events],
        limit=limit,
        offset=offset,
    )


@router.get("/analytics", response_model=DashboardAnalytics)
async def get_dashboard_analytics(
    window_minutes: int = 60,
    bucket_minutes: int = 10,
    project_id: str = Depends(check_rate_limit),
):
    """Return query analytics for ACE dashboard insights."""
    _ = project_id
    data = get_query_analytics(window_minutes=window_minutes, bucket_minutes=bucket_minutes)
    return DashboardAnalytics(**data)


@router.get("/sessions")
async def get_all_sessions(
    namespace: str = "default",
    limit: int = 20,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    """List sessions for 'Session Inspector'."""
    query = (
        select(SessionProgress)
        .where(SessionProgress.project_id == project_id)
        .order_by(desc(SessionProgress.updated_at))
        .limit(limit)
    )
    result = await db.execute(query)
    sessions = result.scalars().all()
    _ = namespace
    return {"sessions": sessions}


def _event_to_response(event: MemoryEvent) -> TimelineEvent:
    return TimelineEvent(
        event_id=event.event_id,
        memory_id=event.memory_id,
        project_id=event.project_id,
        namespace=event.namespace,
        agent_id=event.agent_id,
        event_type=event.event_type,
        event_payload=event.event_payload or {},
        created_at=event.created_at,
    )
