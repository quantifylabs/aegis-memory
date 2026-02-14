"""
ACE Evaluation Router (~60 lines)

Handles: /memories/ace/eval/metrics, /memories/ace/eval/correlation
"""

from api.dependencies.auth import check_rate_limit
from api.dependencies.database import get_read_db
from eval_repository import EvalRepository
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class EvalMetricsResponse(BaseModel):
    success_rate: float
    retrieval_precision: float
    pollution_rate: float
    mttr_seconds: float
    total_tasks: int
    passing_tasks: int
    total_memories: int
    helpful_votes: int
    harmful_votes: int
    window: str


class EvalCorrelationResponse(BaseModel):
    correlation_score: float
    prob_pass_given_helpful: float
    prob_pass_given_harmful: float
    sample_size: int
    helpful_count: int
    harmful_count: int


@router.get("/eval/metrics", response_model=EvalMetricsResponse)
async def get_evaluation_metrics(
    namespace: str | None = None, agent_id: str | None = None,
    window: str = "global",
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    """Get aggregated evaluation metrics."""
    if window not in ["24h", "7d", "30d", "global"]:
        raise HTTPException(status_code=400, detail="Invalid window. Use 24h, 7d, 30d, or global.")
    metrics = await EvalRepository.get_metrics(db, project_id=project_id, namespace=namespace, agent_id=agent_id, window=window)
    return EvalMetricsResponse(**metrics)


@router.get("/eval/correlation", response_model=EvalCorrelationResponse)
async def get_vote_utility_correlation(
    namespace: str | None = None, agent_id: str | None = None,
    window: str = "global",
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    """Calculate correlation between memory votes and task success."""
    correlation = await EvalRepository.get_vote_utility_correlation(db, project_id=project_id, namespace=namespace, agent_id=agent_id, window=window)
    return EvalCorrelationResponse(**correlation)
