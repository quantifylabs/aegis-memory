"""
ACE Feature Tracking Router (~130 lines)

Handles: /memories/ace/feature, /memories/ace/feature/{id}, /memories/ace/features
"""

from datetime import datetime

from ace_repository import ACERepository
from api.dependencies.auth import check_rate_limit
from api.dependencies.database import get_db, get_read_db
from fastapi import APIRouter, Depends, HTTPException
from models import FeatureStatus
from observability import OperationNames, record_operation, track_latency
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class FeatureCreate(BaseModel):
    feature_id: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1, max_length=10_000)
    session_id: str | None = None
    namespace: str = "default"
    category: str | None = None
    test_steps: list[str] | None = None


class FeatureUpdate(BaseModel):
    status: str | None = None
    passes: bool | None = None
    implemented_by: str | None = None
    verified_by: str | None = None
    implementation_notes: str | None = None
    failure_reason: str | None = None
    task_id: str | None = Field(default=None, max_length=128)
    retrieval_event_id: str | None = Field(default=None, max_length=32)
    selected_memory_ids: list[str] | None = None


class FeatureResponse(BaseModel):
    id: str
    feature_id: str
    description: str
    category: str | None
    status: str
    passes: bool
    test_steps: list[str]
    implemented_by: str | None
    verified_by: str | None
    updated_at: datetime


class FeatureListResponse(BaseModel):
    features: list[FeatureResponse]
    total: int
    passing: int
    failing: int
    in_progress: int


def _feature_to_response(feature) -> FeatureResponse:
    return FeatureResponse(
        id=feature.id, feature_id=feature.feature_id, description=feature.description,
        category=feature.category, status=feature.status, passes=feature.passes,
        test_steps=feature.test_steps or [], implemented_by=feature.implemented_by,
        verified_by=feature.verified_by, updated_at=feature.updated_at,
    )


@router.post("/feature", response_model=FeatureResponse)
async def create_feature(body: FeatureCreate, project_id: str = Depends(check_rate_limit), db: AsyncSession = Depends(get_db)):
    """Create a feature to track."""
    feature = await ACERepository.create_feature(db, project_id=project_id, feature_id=body.feature_id, description=body.description, session_id=body.session_id, namespace=body.namespace, category=body.category, test_steps=body.test_steps)
    return _feature_to_response(feature)


@router.get("/feature/{feature_id}", response_model=FeatureResponse)
async def get_feature(feature_id: str, namespace: str = "default", project_id: str = Depends(check_rate_limit), db: AsyncSession = Depends(get_read_db)):
    """Get feature by feature_id."""
    feature = await ACERepository.get_feature(db, feature_id, project_id, namespace)
    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found")
    return _feature_to_response(feature)


@router.patch("/feature/{feature_id}", response_model=FeatureResponse)
async def update_feature(feature_id: str, body: FeatureUpdate, namespace: str = "default", project_id: str = Depends(check_rate_limit), db: AsyncSession = Depends(get_db)):
    """Update feature status."""
    feature = await ACERepository.update_feature(db, feature_id=feature_id, project_id=project_id, namespace=namespace, status=body.status, passes=body.passes, implemented_by=body.implemented_by, verified_by=body.verified_by, implementation_notes=body.implementation_notes, failure_reason=body.failure_reason, task_id=body.task_id, retrieval_event_id=body.retrieval_event_id, selected_memory_ids=body.selected_memory_ids)
    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found")
    return _feature_to_response(feature)


@router.get("/features", response_model=FeatureListResponse)
async def list_features(namespace: str = "default", session_id: str | None = None, status: str | None = None, project_id: str = Depends(check_rate_limit), db: AsyncSession = Depends(get_read_db)):
    """List all features with status summary."""
    features = await ACERepository.list_features(db, project_id=project_id, namespace=namespace, session_id=session_id, status=status)
    total = len(features)
    passing = sum(1 for f in features if f.passes)
    failing = sum(1 for f in features if f.status == FeatureStatus.FAILED.value)
    in_prog = sum(1 for f in features if f.status == FeatureStatus.IN_PROGRESS.value)
    return FeatureListResponse(features=[_feature_to_response(f) for f in features], total=total, passing=passing, failing=failing, in_progress=in_prog)
