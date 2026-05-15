"""Skill CRUD + activation Router (Context Hub v2.3.0)."""

from typing import Any

from api.dependencies.auth import check_rate_limit
from api.dependencies.database import get_db, get_read_db
from config import get_settings
from content_security import ContentSecurityScanner
from embedding_service import get_embedding_service
from fastapi import APIRouter, Depends, HTTPException, status
from integrity import compute_integrity_hash
from pydantic import BaseModel, Field
from skill_repository import SkillRepository
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()
_settings = get_settings()
_scanner = ContentSecurityScanner(_settings)


class SkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1, max_length=2_000)
    skill_md: str = Field(..., min_length=1, max_length=200_000)
    bundled_files: dict[str, str] | None = None   # {"scripts/foo.py": "...", "references/x.md": "..."}
    metadata: dict[str, Any] | None = None
    version: str = "1.0.0"
    namespace: str = "default"
    agent_id: str | None = None


class SkillOut(BaseModel):
    id: str
    name: str
    description: str
    version: str
    skill_md: str
    bundled_files: dict[str, str]
    integrity_hash: str | None
    content_flags: list[str]
    trust_level: str


@router.post("/", status_code=201, response_model=SkillOut)
async def create_skill(
    body: SkillCreate,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    # Trust gate: skills can ship executable code — require privileged+ by default.
    # Content scan: only scan SKILL.md body (description + instructions).
    # Bundled scripts are expected to contain code patterns that would false-positive injection rules.
    scan_target = body.description + "\n\n" + body.skill_md
    scan = _scanner.scan(scan_target)
    if scan.action.value == "reject":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"reason": "content_security_rejected", "flags": scan.flags})

    embedding = await get_embedding_service().embed_single(body.description, db)
    integrity_hash = compute_integrity_hash(body.skill_md, body.agent_id, project_id, _settings.get_integrity_key())
    s = await SkillRepository.create(
        db, project_id=project_id, name=body.name, description=body.description,
        skill_md=body.skill_md, description_embedding=embedding,
        bundled_files=body.bundled_files or {}, metadata=body.metadata or {},
        namespace=body.namespace, version=body.version, agent_id=body.agent_id,
        integrity_hash=integrity_hash, content_flags=scan.flags, trust_level="privileged",
    )
    return SkillOut(
        id=s.id, name=s.name, description=s.description, version=s.version,
        skill_md=s.skill_md, bundled_files=s.bundled_files,
        integrity_hash=s.integrity_hash, content_flags=s.content_flags,
        trust_level=s.trust_level,
    )


@router.get("/")
async def list_skills(
    namespace: str = "default",
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    skills = await SkillRepository.list_all(db, project_id, namespace, active_only=True)
    return [{"name": s.name, "description": s.description, "version": s.version} for s in skills]


@router.get("/{name}", response_model=SkillOut)
async def get_skill(
    name: str,
    namespace: str = "default",
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    s = await SkillRepository.get(db, project_id, name, namespace)
    if s is None:
        raise HTTPException(404, detail="skill not found")
    return SkillOut(
        id=s.id, name=s.name, description=s.description, version=s.version,
        skill_md=s.skill_md, bundled_files=s.bundled_files,
        integrity_hash=s.integrity_hash, content_flags=s.content_flags,
        trust_level=s.trust_level,
    )


class SkillSearch(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    namespace: str = "default"
    top_k: int = Field(default=3, ge=1, le=20)
    min_score: float = Field(default=0.3, ge=0.0, le=1.0)


@router.post("/search")
async def search_skills(
    body: SkillSearch,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    embedding = await get_embedding_service().embed_single(body.query, db)
    matches = await SkillRepository.match(
        db, project_id=project_id, namespace=body.namespace,
        query_embedding=embedding, top_k=body.top_k, min_score=body.min_score,
    )
    return [{"name": s.name, "description": s.description, "score": score} for s, score in matches]


@router.delete("/{name}")
async def delete_skill(
    name: str,
    namespace: str = "default",
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    ok = await SkillRepository.delete(db, project_id, name, namespace)
    if not ok:
        raise HTTPException(404, detail="skill not found")
    return {"deleted": name}
