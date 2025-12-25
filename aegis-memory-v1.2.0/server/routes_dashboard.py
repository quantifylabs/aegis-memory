from typing import List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime, timedelta

from database import get_read_db
from models import Memory, MemoryType, SessionProgress, FeatureTracker
from routes import check_rate_limit

router = APIRouter(prefix="/memories/ace/dashboard", tags=["dashboard"])

class DashboardStats(BaseModel):
    total_memories: int
    total_reflections: int
    total_strategies: int
    total_features: int
    recent_activity_count: int
    top_agents: List[dict]

class ActivityItem(BaseModel):
    id: str
    memory_type: str
    content_preview: str
    agent_id: Optional[str]
    effectiveness_score: float
    bullet_helpful: int
    bullet_harmful: int
    created_at: datetime
    error_pattern: Optional[str]

class ActivityFeed(BaseModel):
    items: List[ActivityItem]

@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    namespace: str = "default",
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    """Aggregate stats for the 'The Brain' view."""
    
    # 1. Counts by type
    # Note: In production, cache these queries or use estimates for scale
    total_memories = await db.scalar(
        select(func.count(Memory.id)).where(Memory.project_id == project_id)
    )
    
    total_reflections = await db.scalar(
        select(func.count(Memory.id)).where(
            Memory.project_id == project_id, 
            Memory.memory_type == MemoryType.REFLECTION.value
        )
    )
    
    total_strategies = await db.scalar(
        select(func.count(Memory.id)).where(
            Memory.project_id == project_id, 
            Memory.memory_type == MemoryType.STRATEGY.value
        )
    )

    total_features = await db.scalar(
        select(func.count(FeatureTracker.id)).where(FeatureTracker.project_id == project_id)
    )
    
    # 2. Activity in last 24h
    yesterday = datetime.utcnow() - timedelta(hours=24)
    recent_activity = await db.scalar(
        select(func.count(Memory.id)).where(
            Memory.project_id == project_id,
            Memory.created_at >= yesterday
        )
    )
    
    # 3. Top Agents (by memory count)
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
    
    return DashboardStats(
        total_memories=total_memories or 0,
        total_reflections=total_reflections or 0,
        total_strategies=total_strategies or 0,
        total_features=total_features or 0,
        recent_activity_count=recent_activity or 0,
        top_agents=top_agents
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
        items.append(ActivityItem(
            id=m.id,
            memory_type=m.memory_type,
            content_preview=m.content[:200] + "..." if len(m.content) > 200 else m.content,
            agent_id=m.agent_id,
            effectiveness_score=m.get_effectiveness_score(),
            bullet_helpful=m.bullet_helpful,
            bullet_harmful=m.bullet_harmful,
            created_at=m.created_at,
            error_pattern=m.error_pattern
        ))
        
    return ActivityFeed(items=items)

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
    return {"sessions": sessions}