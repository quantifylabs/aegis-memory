"""Memory Edges Router (v2.4.0)."""

from api.dependencies.auth import check_rate_limit
from api.dependencies.database import get_db, get_read_db
from event_repository import EventRepository
from fastapi import APIRouter, Depends, HTTPException
from memory_graph import EdgeResolution, EdgeType, MemoryGraphRepository
from models import MemoryEventType
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


class EdgeCreate(BaseModel):
    source_memory_id: str = Field(..., max_length=32)
    target_memory_id: str = Field(..., max_length=32)
    edge_type: str = Field(
        ...,
        description="supersedes|contradicts|generalizes|elaborates|derives_from|entity_rel",
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict | None = None


class EdgeResolve(BaseModel):
    resolution: str = Field(
        ...,
        description="kept_source|kept_target|both_valid|both_invalid",
    )
    resolved_by: str | None = None


@router.post("/", status_code=201)
async def create_edge(
    body: EdgeCreate,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    if body.edge_type not in {e.value for e in EdgeType}:
        raise HTTPException(
            400, detail=f"edge_type must be one of: {[e.value for e in EdgeType]}"
        )
    edge = await MemoryGraphRepository.add_edge(
        db,
        project_id=project_id,
        source_id=body.source_memory_id,
        target_id=body.target_memory_id,
        edge_type=body.edge_type,
        confidence=body.confidence,
        detected_by="manual",
        metadata=body.metadata or {},
    )
    await EventRepository.create_event(
        db,
        memory_id=body.source_memory_id,
        project_id=project_id,
        namespace="default",
        agent_id=None,
        event_type=MemoryEventType.EDGE_CREATED.value,
        event_payload={"edge_id": edge.id, "edge_type": body.edge_type},
    )
    return {"id": edge.id, "edge_type": edge.edge_type, "resolution": edge.resolution}


@router.post("/{edge_id}/resolve")
async def resolve_edge(
    edge_id: str,
    body: EdgeResolve,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    if (
        body.resolution not in {r.value for r in EdgeResolution}
        or body.resolution == EdgeResolution.UNRESOLVED.value
    ):
        raise HTTPException(400, detail="invalid resolution")
    edge = await MemoryGraphRepository.resolve(
        db, edge_id, body.resolution, body.resolved_by
    )
    if edge is None:
        raise HTTPException(404, detail="edge not found")
    await EventRepository.create_event(
        db,
        memory_id=edge.source_memory_id,
        project_id=project_id,
        namespace="default",
        agent_id=body.resolved_by,
        event_type=MemoryEventType.EDGE_RESOLVED.value,
        event_payload={"edge_id": edge.id, "resolution": body.resolution},
    )
    return {
        "id": edge.id,
        "resolution": edge.resolution,
        "resolved_at": edge.resolved_at,
    }


@router.get("/for-memory/{memory_id}")
async def edges_for_memory(
    memory_id: str,
    edge_type: str | None = None,
    include_resolved: bool = False,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    edges = await MemoryGraphRepository.get_edges_for_memory(
        db,
        memory_id=memory_id,
        project_id=project_id,
        edge_type=edge_type,
        include_resolved=include_resolved,
    )
    return [
        {
            "id": e.id,
            "source": e.source_memory_id,
            "target": e.target_memory_id,
            "edge_type": e.edge_type,
            "confidence": e.confidence,
            "resolution": e.resolution,
            "detected_by": e.detected_by,
            "detected_at": e.detected_at,
            "metadata": e.metadata_json,
        }
        for e in edges
    ]
