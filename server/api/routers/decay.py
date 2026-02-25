"""
Decay Router — Temporal Decay Configuration and Archive Sweep (v1.9.2)

Endpoints:
  GET  /memories/decay/config   → half-life table + formula description
  POST /memories/decay/archive  → soft-deprecate memories below relevance threshold
"""

from fastapi import APIRouter, Depends
from memory_repository import MemoryRepository
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from temporal_decay import DEFAULT_HALF_LIFE, HALF_LIVES

from api.dependencies.auth import check_rate_limit
from api.dependencies.database import get_db

router = APIRouter()

DECAY_FORMULA = (
    "decay_factor = exp(-ln(2)/half_life_days * age_days); "
    "age_days uses last_accessed_at falling back to created_at; "
    "relevance_score = effectiveness_score * decay_factor"
)
THRESHOLD_DEFAULT = 0.1


# ---------- Models ----------

class DecayConfigResponse(BaseModel):
    half_lives: dict[str, int]
    default_half_life: int
    formula: str
    threshold_default: float


class ArchiveRequest(BaseModel):
    namespace: str = "default"
    threshold: float = Field(default=THRESHOLD_DEFAULT, ge=0.0, le=1.0)
    dry_run: bool = False


class ArchiveResponse(BaseModel):
    archived: int
    namespace: str
    threshold: float
    dry_run: bool


# ---------- Endpoints ----------

@router.get("/config", response_model=DecayConfigResponse)
async def get_decay_config(project_id: str = Depends(check_rate_limit)):
    """
    Return the current temporal decay configuration.

    Includes per-type half-life table, the decay formula, and the
    default threshold used by the archive sweep.
    """
    return DecayConfigResponse(
        half_lives=HALF_LIVES,
        default_half_life=DEFAULT_HALF_LIFE,
        formula=DECAY_FORMULA,
        threshold_default=THRESHOLD_DEFAULT,
    )


@router.post("/archive", response_model=ArchiveResponse)
async def archive_stale_memories(
    body: ArchiveRequest,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    Soft-deprecate memories whose relevance_score falls below threshold.

    Uses the existing is_deprecated / deprecated_at soft-delete columns.
    Set dry_run=True to preview how many memories would be archived without
    actually modifying any rows.
    """
    archived = await MemoryRepository.archive_stale(
        db,
        project_id=project_id,
        namespace=body.namespace,
        threshold=body.threshold,
        dry_run=body.dry_run,
    )
    return ArchiveResponse(
        archived=archived,
        namespace=body.namespace,
        threshold=body.threshold,
        dry_run=body.dry_run,
    )
