"""
ACE Votes Router (~60 lines)

Handles: /memories/ace/vote/{memory_id}
"""

from typing import Literal

from ace_repository import ACERepository
from api.dependencies.auth import check_rate_limit
from api.dependencies.database import get_db
from fastapi import APIRouter, Depends, HTTPException
from observability import OperationNames, record_operation, track_latency
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class VoteRequest(BaseModel):
    vote: Literal["helpful", "harmful"]
    voter_agent_id: str = Field(..., min_length=1, max_length=64)
    context: str | None = Field(default=None, max_length=1000)
    task_id: str | None = Field(default=None, max_length=64)


class VoteResponse(BaseModel):
    memory_id: str
    bullet_helpful: int
    bullet_harmful: int
    effectiveness_score: float


@router.post("/vote/{memory_id}", response_model=VoteResponse)
async def vote_memory(
    memory_id: str,
    body: VoteRequest,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """Vote on a memory's usefulness."""
    try:
        with track_latency(OperationNames.MEMORY_VOTE):
            memory = await ACERepository.vote_memory(
                db, memory_id=memory_id, project_id=project_id,
                voter_agent_id=body.voter_agent_id, vote=body.vote,
                context=body.context, task_id=body.task_id,
            )
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")
        record_operation(OperationNames.MEMORY_VOTE, "success")
        return VoteResponse(
            memory_id=memory.id, bullet_helpful=memory.bullet_helpful,
            bullet_harmful=memory.bullet_harmful,
            effectiveness_score=memory.get_effectiveness_score(),
        )
    except HTTPException:
        raise
    except Exception:
        record_operation(OperationNames.MEMORY_VOTE, "error")
        raise
