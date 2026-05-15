"""Context Bundle Router (Context Hub v2.3.0) — POST /context/load."""

from api.dependencies.auth import check_rate_limit
from api.dependencies.database import get_read_db
from context_bundle import ContextBundleService
from event_repository import EventRepository
from fastapi import APIRouter, Depends
from models import MemoryEventType
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


class ContextLoadRequest(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=64)
    query: str | None = Field(default=None, max_length=10_000)
    task_type: str | None = Field(default=None, max_length=64)
    namespace: str = "default"
    token_budget: int = Field(default=8000, ge=500, le=200_000)
    prompt_name: str | None = None
    include_skills: bool = True
    include_subagents: bool = True
    memory_top_k: int = Field(default=10, ge=1, le=50)
    skill_top_k: int = Field(default=3, ge=0, le=20)
    apply_decay: bool = True
    budget_split: dict[str, float] | None = None


@router.post("/load")
async def load_context(
    body: ContextLoadRequest,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    bundle = await ContextBundleService.load(
        db,
        project_id=project_id,
        agent_id=body.agent_id,
        query=body.query,
        task_type=body.task_type,
        namespace=body.namespace,
        token_budget=body.token_budget,
        prompt_name=body.prompt_name,
        include_skills=body.include_skills,
        include_subagents=body.include_subagents,
        memory_top_k=body.memory_top_k,
        skill_top_k=body.skill_top_k,
        apply_decay=body.apply_decay,
        budget_split=body.budget_split,
    )

    await EventRepository.create_event(
        db,
        memory_id=None,
        project_id=project_id,
        namespace=body.namespace,
        agent_id=body.agent_id,
        event_type=MemoryEventType.CONTEXT_LOADED.value,
        event_payload={
            "task_type": body.task_type,
            "tokens_used": bundle.tokens_used,
            "tokens_budget": bundle.tokens_budget,
            "items_count": len(bundle.items),
            "integrity_all_verified": bundle.integrity_all_verified,
        },
    )

    return {
        "agent_id": bundle.agent_id,
        "task_type": bundle.task_type,
        "query": bundle.query,
        "tokens_budget": bundle.tokens_budget,
        "tokens_used": bundle.tokens_used,
        "integrity_all_verified": bundle.integrity_all_verified,
        "items": [
            {
                "kind": i.kind, "id": i.id, "name": i.name,
                "content": i.content, "score": i.score,
                "integrity_verified": i.integrity_verified,
                "tokens_estimated": i.tokens_estimated,
                "metadata": i.metadata,
            } for i in bundle.items
        ],
    }
