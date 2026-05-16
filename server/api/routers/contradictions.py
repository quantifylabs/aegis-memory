"""Contradictions Router (v2.4.0) -- detection, listing, metrics."""

from api.dependencies.auth import check_rate_limit
from api.dependencies.database import get_db, get_read_db
from contradiction_detector import ContradictionDetector
from fastapi import APIRouter, Depends, HTTPException
from memory_graph import MemoryGraphRepository
from models import Memory
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


class ScanRequest(BaseModel):
    memory_id: str | None = None              # if given, scan only this memory
    namespace: str = "default"
    similarity_threshold: float = Field(default=0.80, ge=0.5, le=0.99)
    top_neighbors: int = Field(default=5, ge=1, le=20)
    use_llm: bool = False                      # stage-2 LLM confirmation
    batch_limit: int = Field(default=100, ge=1, le=1000)


@router.post("/scan")
async def scan_for_contradictions(
    body: ScanRequest,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    On-demand contradiction scan.

    - If memory_id given: scan that one memory against its neighbors.
    - If not: batch-scan the most recent N memories.
    """
    llm = None
    if body.use_llm:
        # Wire up your LLM adapter here. Skipping concrete impl --
        # mirror the InjectionClassifier wiring in memories.py.
        raise HTTPException(501, detail="LLM contradiction adapter not yet configured")

    detector = ContradictionDetector(
        similarity_threshold=body.similarity_threshold, llm=llm
    )

    if body.memory_id:
        result = await db.execute(select(Memory).where(Memory.id == body.memory_id))
        memory = result.scalar_one_or_none()
        if memory is None:
            raise HTTPException(404, detail="memory not found")
        edge_ids = await detector.detect_and_record(
            db, memory=memory, top_neighbors=body.top_neighbors
        )
        return {
            "memory_id": body.memory_id,
            "edges_created": edge_ids,
            "count": len(edge_ids),
        }

    # Batch mode
    result = await db.execute(
        select(Memory).where(
            (Memory.project_id == project_id) & (Memory.namespace == body.namespace)
        ).order_by(Memory.created_at.desc()).limit(body.batch_limit)
    )
    total_edges = 0
    scanned = 0
    for memory in result.scalars():
        edge_ids = await detector.detect_and_record(
            db, memory=memory, top_neighbors=body.top_neighbors
        )
        total_edges += len(edge_ids)
        scanned += 1
    return {"scanned": scanned, "edges_created": total_edges}


@router.get("/")
async def list_unresolved(
    limit: int = 100,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    edges = await MemoryGraphRepository.list_unresolved_contradictions(
        db, project_id, limit=limit
    )
    return [
        {
            "id": e.id,
            "source": e.source_memory_id,
            "target": e.target_memory_id,
            "confidence": e.confidence,
            "detected_by": e.detected_by,
            "detected_at": e.detected_at,
            "metadata": e.metadata_json,
        }
        for e in edges
    ]


@router.get("/metrics")
async def contradiction_metrics(
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    """Counters for Simulation Reliability Index."""
    return await MemoryGraphRepository.contradiction_metrics(db, project_id)
