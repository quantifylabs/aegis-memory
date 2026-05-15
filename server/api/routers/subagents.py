"""Subagent CRUD Router (Context Hub v2.3.0)."""

from api.dependencies.auth import check_rate_limit
from api.dependencies.database import get_db, get_read_db
from config import get_settings
from fastapi import APIRouter, Depends, HTTPException
from integrity import compute_integrity_hash
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from subagent_repository import SubagentRepository


router = APIRouter()
_settings = get_settings()


class SubagentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1, max_length=2000)
    system_prompt: str | None = None
    system_prompt_ref: str | None = None
    model: str | None = None
    tools: list[str] | None = None
    allowed_scopes: list[str] | None = None
    allowed_skills: list[str] | None = None
    parent_agent_id: str | None = None
    namespace: str = "default"


class SubagentOut(BaseModel):
    id: str
    name: str
    description: str
    system_prompt: str | None
    system_prompt_ref: str | None
    model: str | None
    tools: list[str]
    allowed_scopes: list[str]
    allowed_skills: list[str]
    parent_agent_id: str | None


@router.post("/", status_code=201, response_model=SubagentOut)
async def create_subagent(
    body: SubagentCreate,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    if not body.system_prompt and not body.system_prompt_ref:
        raise HTTPException(400, detail="system_prompt or system_prompt_ref required")

    canonical = body.system_prompt or body.system_prompt_ref or ""
    integrity_hash = compute_integrity_hash(canonical, body.parent_agent_id, project_id, _settings.get_integrity_key())

    s = await SubagentRepository.create(
        db, project_id=project_id, name=body.name, description=body.description,
        system_prompt=body.system_prompt, system_prompt_ref=body.system_prompt_ref,
        model=body.model, tools=body.tools, allowed_scopes=body.allowed_scopes,
        allowed_skills=body.allowed_skills, parent_agent_id=body.parent_agent_id,
        namespace=body.namespace, integrity_hash=integrity_hash,
    )
    return SubagentOut(
        id=s.id, name=s.name, description=s.description,
        system_prompt=s.system_prompt, system_prompt_ref=s.system_prompt_ref,
        model=s.model, tools=s.tools, allowed_scopes=s.allowed_scopes,
        allowed_skills=s.allowed_skills, parent_agent_id=s.parent_agent_id,
    )


@router.get("/{name}", response_model=SubagentOut)
async def get_subagent(
    name: str,
    namespace: str = "default",
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    s = await SubagentRepository.get(db, project_id, name, namespace)
    if s is None:
        raise HTTPException(404, detail="subagent not found")
    return SubagentOut(
        id=s.id, name=s.name, description=s.description,
        system_prompt=s.system_prompt, system_prompt_ref=s.system_prompt_ref,
        model=s.model, tools=s.tools, allowed_scopes=s.allowed_scopes,
        allowed_skills=s.allowed_skills, parent_agent_id=s.parent_agent_id,
    )


@router.get("/")
async def list_subagents(
    parent_agent_id: str | None = None,
    namespace: str = "default",
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    subs = await SubagentRepository.list_for_parent(db, project_id, parent_agent_id, namespace)
    return [{"name": s.name, "description": s.description, "model": s.model,
             "tools": s.tools, "parent_agent_id": s.parent_agent_id} for s in subs]
