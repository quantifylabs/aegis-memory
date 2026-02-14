"""
Handoff Router (~60 lines)

Handles: /memories/handoff
"""

from api.dependencies.auth import check_rate_limit
from api.dependencies.database import get_db
from embedding_service import get_embedding_service
from fastapi import APIRouter, BackgroundTasks, Depends
from memory_repository import MemoryRepository
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class HandoffRequest(BaseModel):
    source_agent_id: str
    target_agent_id: str
    namespace: str = "default"
    user_id: str | None = None
    task_context: str | None = Field(default=None, max_length=10_000)
    max_memories: int = Field(default=20, ge=1, le=100)


class HandoffBaton(BaseModel):
    source_agent_id: str
    target_agent_id: str
    namespace: str
    user_id: str | None
    task_context: str | None
    summary: str | None
    active_tasks: list[str]
    blocked_on: list[str]
    recent_decisions: list[str]
    key_facts: list[str]
    memory_ids: list[str]


@router.post("/handoff", response_model=HandoffBaton)
async def handoff(
    body: HandoffRequest,
    background_tasks: BackgroundTasks,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """Generate a structured handoff baton for agent-to-agent state transfer."""
    embed_service = get_embedding_service()
    task_embedding = None
    if body.task_context:
        task_embedding = await embed_service.embed_single(body.task_context, db)
    results = await MemoryRepository.get_agent_memories_for_handoff(
        db, project_id=project_id, source_agent_id=body.source_agent_id,
        namespace=body.namespace, user_id=body.user_id,
        task_embedding=task_embedding, max_memories=body.max_memories,
    )
    memories = [mem for mem, _ in results]
    return HandoffBaton(
        source_agent_id=body.source_agent_id, target_agent_id=body.target_agent_id,
        namespace=body.namespace, user_id=body.user_id, task_context=body.task_context,
        summary=None, active_tasks=[], blocked_on=[], recent_decisions=[],
        key_facts=[mem.content for mem in memories],
        memory_ids=[mem.id for mem in memories],
    )
