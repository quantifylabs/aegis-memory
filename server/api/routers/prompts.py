"""Prompt CRUD Router (Context Hub v2.3.0)."""

from typing import Any

from api.dependencies.auth import check_rate_limit
from api.dependencies.database import get_db, get_read_db
from config import get_settings
from content_security import ContentSecurityScanner
from fastapi import APIRouter, Depends, HTTPException, status
from integrity import compute_integrity_hash
from prompt_repository import PromptRepository
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()
_settings = get_settings()
_scanner = ContentSecurityScanner(_settings)


class PromptCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    content: str = Field(..., min_length=1, max_length=100_000)
    namespace: str = "default"
    description: str | None = None
    tags: list[str] | None = None
    agent_id: str | None = None
    activate: bool = True


class PromptOut(BaseModel):
    id: str
    name: str
    version: int
    content: str
    variables: list[str]
    tags: list[str]
    is_active: bool
    integrity_hash: str | None
    content_flags: list[str]
    created_at: Any


@router.post("/", status_code=201, response_model=PromptOut)
async def create_prompt(
    body: PromptCreate,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    scan = _scanner.scan(body.content)
    if scan.action.value == "reject":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"reason": "content_security_rejected", "flags": scan.flags})
    final_content = scan.content if scan.action.value == "redact" else body.content
    integrity_hash = compute_integrity_hash(final_content, body.agent_id, project_id, _settings.get_integrity_key())
    p = await PromptRepository.create(
        db, project_id=project_id, name=body.name, content=final_content,
        namespace=body.namespace, description=body.description, tags=body.tags,
        agent_id=body.agent_id, integrity_hash=integrity_hash,
        content_flags=scan.flags, activate=body.activate,
    )
    return PromptOut(
        id=p.id, name=p.name, version=p.version, content=p.content, variables=p.variables,
        tags=p.tags, is_active=p.is_active, integrity_hash=p.integrity_hash,
        content_flags=p.content_flags, created_at=p.created_at,
    )


@router.get("/{name}", response_model=PromptOut)
async def get_prompt(
    name: str,
    namespace: str = "default",
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    p = await PromptRepository.get_active(db, project_id, name, namespace)
    if p is None:
        raise HTTPException(404, detail="prompt not found or no active version")
    return PromptOut(
        id=p.id, name=p.name, version=p.version, content=p.content, variables=p.variables,
        tags=p.tags, is_active=p.is_active, integrity_hash=p.integrity_hash,
        content_flags=p.content_flags, created_at=p.created_at,
    )


@router.get("/{name}/versions")
async def list_versions(
    name: str,
    namespace: str = "default",
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    versions = await PromptRepository.list_versions(db, project_id, name, namespace)
    return [{"id": v.id, "version": v.version, "is_active": v.is_active, "created_at": v.created_at} for v in versions]


@router.post("/{name}/activate/{version}")
async def activate_version(
    name: str, version: int,
    namespace: str = "default",
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    p = await PromptRepository.activate(db, project_id, name, version, namespace)
    if p is None or p.version != version:
        raise HTTPException(404, detail="version not found")
    return {"activated": {"name": name, "version": version}}
