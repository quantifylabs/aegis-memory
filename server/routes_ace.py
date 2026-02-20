"""
Aegis ACE-Enhanced Routes

Endpoints inspired by:
1. ACE Paper (Stanford/SambaNova) - Agentic Context Engineering
2. Anthropic's Long-Running Agent Harnesses

New Capabilities:
- Memory voting (helpful/harmful)
- Incremental delta updates
- Session progress tracking
- Feature status tracking
- Reflection memory creation
"""

import time
from datetime import datetime
from typing import Any, Literal

from ace_repository import ACERepository
from auth import get_project_id
from config import get_settings
from database import get_db, get_read_db
from embedding_service import get_embedding_service
from eval_repository import EvalRepository
from event_repository import EventRepository
from fastapi import APIRouter, Depends, HTTPException
from memory_repository import MemoryRepository
from models import FeatureStatus, MemoryEventType, MemoryScope, MemoryType
from observability import OperationNames, record_operation, track_latency
from pydantic import BaseModel, Field
from rate_limiter import RateLimiter, RateLimitExceeded
from routes import check_rate_limit
from scope_inference import ScopeInference
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/ace", tags=["ACE"])
settings = get_settings()


# ---------- Request/Response Models ----------

class VoteRequest(BaseModel):
    """Vote on a memory's usefulness."""
    vote: Literal["helpful", "harmful"]
    voter_agent_id: str = Field(..., min_length=1, max_length=64)
    context: str | None = Field(default=None, max_length=1000)
    task_id: str | None = Field(default=None, max_length=64)


class VoteResponse(BaseModel):
    memory_id: str
    bullet_helpful: int
    bullet_harmful: int
    effectiveness_score: float


class DeltaOperation(BaseModel):
    """Single delta operation for incremental updates."""
    type: Literal["add", "update", "deprecate"]

    # For add operations
    content: str | None = Field(default=None, max_length=100_000)
    memory_type: str | None = Field(default=MemoryType.STANDARD.value)
    agent_id: str | None = None
    user_id: str | None = None
    namespace: str = "default"
    scope: str | None = None
    metadata: dict[str, Any] | None = None
    ttl_seconds: int | None = None

    # For update/deprecate operations
    memory_id: str | None = None

    # For update - partial metadata update
    metadata_patch: dict[str, Any] | None = None

    # For deprecate
    superseded_by: str | None = None
    deprecation_reason: str | None = None


class DeltaRequest(BaseModel):
    """Batch of delta operations."""
    operations: list[DeltaOperation] = Field(..., min_length=1, max_length=100)


class DeltaResultItem(BaseModel):
    operation: str
    success: bool
    memory_id: str | None = None
    error: str | None = None


class DeltaResponse(BaseModel):
    results: list[DeltaResultItem]
    total_time_ms: float


class ReflectionCreate(BaseModel):
    """Create a reflection memory from agent trajectory analysis."""
    content: str = Field(..., min_length=1, max_length=100_000)
    agent_id: str = Field(..., min_length=1, max_length=64)
    user_id: str | None = None
    namespace: str = "default"

    # Reflection-specific fields
    source_trajectory_id: str | None = Field(default=None, max_length=64)
    error_pattern: str | None = Field(default=None, max_length=128)
    correct_approach: str | None = Field(default=None, max_length=10_000)
    applicable_contexts: list[str] | None = None

    # Optional scope override (defaults to global for reflections)
    scope: str | None = None
    metadata: dict[str, Any] | None = None


class ReflectionResponse(BaseModel):
    id: str
    memory_type: str
    scope: str
    effectiveness_score: float


class SessionProgressCreate(BaseModel):
    """Create or update session progress."""
    session_id: str = Field(..., min_length=1, max_length=64)
    agent_id: str | None = None
    user_id: str | None = None
    namespace: str = "default"


class SessionProgressUpdate(BaseModel):
    """Update session progress."""
    completed_items: list[str] | None = None
    in_progress_item: str | None = None
    next_items: list[str] | None = None
    blocked_items: list[dict[str, str]] | None = None  # [{item: "x", reason: "y"}]
    summary: str | None = None
    last_action: str | None = None
    status: str | None = None
    total_items: int | None = None


class SessionProgressResponse(BaseModel):
    id: str
    session_id: str
    status: str
    completed_count: int
    total_items: int
    progress_percent: float
    completed_items: list[str]
    in_progress_item: str | None
    next_items: list[str]
    blocked_items: list[dict]
    summary: str | None
    last_action: str | None
    updated_at: datetime


class FeatureCreate(BaseModel):
    """Create a feature to track."""
    feature_id: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1, max_length=10_000)
    session_id: str | None = None
    namespace: str = "default"
    category: str | None = None
    test_steps: list[str] | None = None


class FeatureUpdate(BaseModel):
    """Update feature status."""
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


class RunCreate(BaseModel):
    """Start tracking an agent run."""
    run_id: str = Field(..., min_length=1, max_length=64)
    agent_id: str | None = Field(default=None, max_length=64)
    task_type: str | None = Field(default=None, max_length=64)
    namespace: str = "default"
    memory_ids_used: list[str] | None = None


class RunComplete(BaseModel):
    """Complete a run with outcome data."""
    success: bool
    evaluation: dict | None = None
    logs: dict | None = None
    auto_vote: bool = True
    auto_reflect: bool = True


class RunResponse(BaseModel):
    run_id: str
    agent_id: str | None
    task_type: str | None
    namespace: str
    status: str
    success: bool | None
    evaluation: dict
    logs: dict
    memory_ids_used: list[str]
    reflection_ids: list[str]
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AgentPlaybookRequest(BaseModel):
    """Query playbook for a specific agent."""
    query: str = Field(..., min_length=1, max_length=10_000)
    agent_id: str = Field(..., min_length=1, max_length=64)
    task_type: str | None = Field(default=None, max_length=64)
    namespace: str = "default"
    top_k: int = Field(default=20, ge=1, le=100)
    min_effectiveness: float = Field(default=-1.0, ge=-1.0, le=1.0)


class CurateRequest(BaseModel):
    """Trigger a curation cycle."""
    namespace: str = "default"
    agent_id: str | None = Field(default=None, max_length=64)
    top_k: int = Field(default=10, ge=1, le=100)
    min_effectiveness_threshold: float = Field(default=-0.3, ge=-1.0, le=1.0)


class CurationEntryResponse(BaseModel):
    id: str
    content: str
    memory_type: str
    effectiveness_score: float
    bullet_helpful: int
    bullet_harmful: int
    total_votes: int


class ConsolidationCandidate(BaseModel):
    memory_id_a: str
    memory_id_b: str
    content_a: str
    content_b: str
    reason: str


class CurationResponse(BaseModel):
    promoted: list[CurationEntryResponse]
    flagged: list[CurationEntryResponse]
    consolidation_candidates: list[ConsolidationCandidate]


class PlaybookQueryRequest(BaseModel):
    """Query for relevant playbook entries (strategies/reflections)."""
    query: str = Field(..., min_length=1, max_length=10_000)
    agent_id: str = Field(..., min_length=1, max_length=64)
    namespace: str = "default"
    include_types: list[str] = Field(
        default=[MemoryType.STRATEGY.value, MemoryType.REFLECTION.value]
    )
    top_k: int = Field(default=20, ge=1, le=100)
    min_effectiveness: float = Field(default=-1.0, ge=-1.0, le=1.0)


class PlaybookEntry(BaseModel):
    id: str
    content: str
    memory_type: str
    effectiveness_score: float
    bullet_helpful: int
    bullet_harmful: int
    error_pattern: str | None
    created_at: datetime


class PlaybookResponse(BaseModel):
    entries: list[PlaybookEntry]
    query_time_ms: float


async def _emit_event(
    db: AsyncSession,
    *,
    project_id: str,
    namespace: str,
    event_type: str,
    memory_id: str | None = None,
    agent_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    await EventRepository.create_event(
        db,
        memory_id=memory_id,
        project_id=project_id,
        namespace=namespace,
        agent_id=agent_id,
        event_type=event_type,
        event_payload=payload or {},
    )


# ---------- Routes ----------

@router.post("/vote/{memory_id}", response_model=VoteResponse)
async def vote_memory(
    memory_id: str,
    body: VoteRequest,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    Vote on a memory's usefulness.

    This enables ACE-style self-improvement where agents can mark
    which memories were helpful or harmful for completing tasks.

    Votes are tracked in history for analysis and the memory's
    bullet_helpful/bullet_harmful counters are updated.
    """
    try:
        with track_latency(OperationNames.MEMORY_VOTE):
            result = await ACERepository.vote_memory(
                db,
                memory_id=memory_id,
                project_id=project_id,
                voter_agent_id=body.voter_agent_id,
                vote=body.vote,
                context=body.context,
                task_id=body.task_id,
            )

        if result is None:
            record_operation(OperationNames.MEMORY_VOTE, "error")
            raise HTTPException(status_code=404, detail="Memory not found")

        record_operation(OperationNames.MEMORY_VOTE, "success")
        return VoteResponse(
            memory_id=memory_id,
            bullet_helpful=result.bullet_helpful,
            bullet_harmful=result.bullet_harmful,
            effectiveness_score=result.get_effectiveness_score(),
        )
    except HTTPException:
        raise
    except Exception:
        record_operation(OperationNames.MEMORY_VOTE, "error")
        raise


@router.post("/delta", response_model=DeltaResponse)
async def apply_delta(
    body: DeltaRequest,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    Apply incremental delta updates to memories.

    ACE Insight: Never rewrite entire context. Instead use incremental
    deltas that add, update, or deprecate individual memories.

    This prevents context collapse where accumulated knowledge is
    accidentally compressed away.

    Operations:
    - add: Create new memory
    - update: Modify existing memory metadata/counters
    - deprecate: Soft-delete memory (preserves history)
    """
    start = time.monotonic()
    embed_service = get_embedding_service()
    results = []

    try:
        with track_latency(OperationNames.MEMORY_DELTA):
            for op in body.operations:
                try:
                    if op.type == "add":
                        if not op.content:
                            results.append(DeltaResultItem(
                                operation="add",
                                success=False,
                                error="Content required for add operation"
                            ))
                            continue

                        with track_latency(OperationNames.MEMORY_DELTA_ADD):
                            embedding = await embed_service.embed_single(op.content, db)

                            default_scope = MemoryScope.GLOBAL if op.memory_type == MemoryType.REFLECTION.value else None
                            resolved_scope = ScopeInference.infer_scope(
                                content=op.content,
                                explicit_scope=op.scope or (default_scope.value if default_scope else None),
                                agent_id=op.agent_id,
                                metadata=op.metadata or {},
                            )

                            mem = await MemoryRepository.add(
                                db,
                                project_id=project_id,
                                content=op.content,
                                embedding=embedding,
                                user_id=op.user_id,
                                agent_id=op.agent_id,
                                namespace=op.namespace,
                                metadata=op.metadata,
                                ttl_seconds=op.ttl_seconds,
                                scope=resolved_scope.value,
                                memory_type=op.memory_type,
                            )

                        await _emit_event(
                            db,
                            project_id=project_id,
                            memory_id=mem.id,
                            namespace=mem.namespace,
                            agent_id=mem.agent_id,
                            event_type=MemoryEventType.CREATED.value,
                            payload={"source": "delta_add", "memory_type": mem.memory_type},
                        )
                        record_operation(OperationNames.MEMORY_DELTA_ADD, "success")
                        results.append(DeltaResultItem(operation="add", success=True, memory_id=mem.id))

                    elif op.type == "update":
                        if not op.memory_id:
                            results.append(DeltaResultItem(
                                operation="update",
                                success=False,
                                error="memory_id required for update operation"
                            ))
                            continue

                        with track_latency(OperationNames.MEMORY_DELTA_UPDATE):
                            updated = await ACERepository.update_memory_metadata(
                                db,
                                memory_id=op.memory_id,
                                project_id=project_id,
                                metadata_patch=op.metadata_patch,
                            )

                        if updated:
                            record_operation(OperationNames.MEMORY_DELTA_UPDATE, "success")
                            results.append(DeltaResultItem(operation="update", success=True, memory_id=op.memory_id))
                        else:
                            record_operation(OperationNames.MEMORY_DELTA_UPDATE, "error")
                            results.append(DeltaResultItem(operation="update", success=False, memory_id=op.memory_id, error="Memory not found"))

                    elif op.type == "deprecate":
                        if not op.memory_id:
                            results.append(DeltaResultItem(
                                operation="deprecate",
                                success=False,
                                error="memory_id required for deprecate operation"
                            ))
                            continue

                        with track_latency(OperationNames.MEMORY_DELTA_DEPRECATE):
                            deprecated = await ACERepository.deprecate_memory(
                                db,
                                memory_id=op.memory_id,
                                project_id=project_id,
                                deprecated_by=op.agent_id,
                                superseded_by=op.superseded_by,
                                reason=op.deprecation_reason,
                            )

                        if deprecated:
                            record_operation(OperationNames.MEMORY_DELTA_DEPRECATE, "success")
                            results.append(DeltaResultItem(operation="deprecate", success=True, memory_id=op.memory_id))
                        else:
                            record_operation(OperationNames.MEMORY_DELTA_DEPRECATE, "error")
                            results.append(DeltaResultItem(operation="deprecate", success=False, memory_id=op.memory_id, error="Memory not found"))

                except Exception as e:
                    if op.type == "add":
                        record_operation(OperationNames.MEMORY_DELTA_ADD, "error")
                    elif op.type == "update":
                        record_operation(OperationNames.MEMORY_DELTA_UPDATE, "error")
                    elif op.type == "deprecate":
                        record_operation(OperationNames.MEMORY_DELTA_DEPRECATE, "error")
                    results.append(DeltaResultItem(operation=op.type, success=False, memory_id=op.memory_id, error=str(e)))

        record_operation(OperationNames.MEMORY_DELTA, "success")
    except Exception:
        record_operation(OperationNames.MEMORY_DELTA, "error")
        raise

    elapsed_ms = (time.monotonic() - start) * 1000
    return DeltaResponse(results=results, total_time_ms=round(elapsed_ms, 2))

@router.post("/reflection", response_model=ReflectionResponse)
async def create_reflection(
    body: ReflectionCreate,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a reflection memory from trajectory analysis.

    ACE Pattern: The Reflector component extracts insights from
    successes and failures. These insights become reflection memories
    that help future tasks avoid the same mistakes.

    Reflections default to GLOBAL scope so all agents can benefit.
    """
    embed_service = get_embedding_service()

    # Generate embedding
    embedding = await embed_service.embed_single(body.content, db)

    # Build metadata
    metadata = body.metadata or {}
    if body.correct_approach:
        metadata["correct_approach"] = body.correct_approach
    if body.applicable_contexts:
        metadata["applicable_contexts"] = body.applicable_contexts

    # Reflections default to global scope
    resolved_scope = ScopeInference.infer_scope(
        content=body.content,
        explicit_scope=body.scope or MemoryScope.GLOBAL.value,
        agent_id=body.agent_id,
        metadata=metadata,
    )

    mem = await ACERepository.create_reflection(
        db,
        project_id=project_id,
        content=body.content,
        embedding=embedding,
        agent_id=body.agent_id,
        user_id=body.user_id,
        namespace=body.namespace,
        scope=resolved_scope.value,
        metadata=metadata,
        source_trajectory_id=body.source_trajectory_id,
        error_pattern=body.error_pattern,
    )

    return ReflectionResponse(
        id=mem.id,
        memory_type=mem.memory_type,
        scope=mem.scope,
        effectiveness_score=mem.get_effectiveness_score(),
    )


@router.post("/playbook", response_model=PlaybookResponse)
async def query_playbook(
    body: PlaybookQueryRequest,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    Query the playbook for relevant strategies and reflections.

    ACE Pattern: Before starting a task, agents should consult the
    playbook for relevant strategies, past mistakes to avoid, and
    proven approaches.

    Results are ranked by semantic similarity and filtered by
    effectiveness score (helpful votes - harmful votes).
    """
    start = time.monotonic()
    embed_service = get_embedding_service()

    query_embedding = await embed_service.embed_single(body.query, db)

    results = await ACERepository.query_playbook(
        db,
        query_embedding=query_embedding,
        project_id=project_id,
        namespace=body.namespace,
        requesting_agent_id=body.agent_id,
        include_types=body.include_types,
        top_k=body.top_k,
        min_effectiveness=body.min_effectiveness,
    )

    elapsed_ms = (time.monotonic() - start) * 1000

    await _emit_event(
        db,
        project_id=project_id,
        namespace=body.namespace,
        agent_id=body.agent_id,
        event_type=MemoryEventType.QUERIED.value,
        payload={"source": "playbook", "query": body.query, "result_count": len(results), "top_k": body.top_k},
    )

    entries = [
        PlaybookEntry(
            id=mem.id,
            content=mem.content,
            memory_type=mem.memory_type,
            effectiveness_score=mem.get_effectiveness_score(),
            bullet_helpful=mem.bullet_helpful,
            bullet_harmful=mem.bullet_harmful,
            error_pattern=mem.error_pattern,
            created_at=mem.created_at,
        )
        for mem, score in results
    ]

    return PlaybookResponse(
        entries=entries,
        query_time_ms=round(elapsed_ms, 2),
    )


# ---------- ACE Run Tracking Routes ----------

@router.post("/run", response_model=RunResponse)
async def create_run(
    body: RunCreate,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    Start tracking an agent run.

    ACE Loop: The Generation phase. Records which memories are being
    used for the current task execution.
    """
    try:
        with track_latency(OperationNames.MEMORY_RUN_CREATE):
            run = await ACERepository.create_run(
                db,
                project_id=project_id,
                run_id=body.run_id,
                agent_id=body.agent_id,
                task_type=body.task_type,
                namespace=body.namespace,
                memory_ids_used=body.memory_ids_used,
            )
        record_operation(OperationNames.MEMORY_RUN_CREATE, "success")
        return _run_to_response(run)
    except Exception:
        record_operation(OperationNames.MEMORY_RUN_CREATE, "error")
        raise


@router.get("/run/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    """Get run details by run_id."""
    try:
        with track_latency(OperationNames.MEMORY_RUN_GET):
            run = await ACERepository.get_run(db, run_id, project_id)

        if not run:
            record_operation(OperationNames.MEMORY_RUN_GET, "error")
            raise HTTPException(status_code=404, detail="Run not found")

        record_operation(OperationNames.MEMORY_RUN_GET, "success")
        return _run_to_response(run)
    except HTTPException:
        raise
    except Exception:
        record_operation(OperationNames.MEMORY_RUN_GET, "error")
        raise


@router.post("/run/{run_id}/complete", response_model=RunResponse)
async def complete_run(
    run_id: str,
    body: RunComplete,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    Complete a run with auto-feedback.

    ACE Loop: The Reflection phase. On completion:
    - Auto-votes memories used (helpful on success, harmful on failure)
    - Auto-creates reflection memories on failure
    - Links run results to playbook entries
    """
    embed_service = get_embedding_service()

    async def embed_fn(content: str) -> list[float]:
        return await embed_service.embed_single(content, db)

    try:
        with track_latency(OperationNames.MEMORY_RUN_COMPLETE):
            run = await ACERepository.complete_run(
                db,
                run_id=run_id,
                project_id=project_id,
                success=body.success,
                evaluation=body.evaluation,
                logs=body.logs,
                auto_vote=body.auto_vote,
                auto_reflect=body.auto_reflect,
                embed_fn=embed_fn,
            )

        if not run:
            record_operation(OperationNames.MEMORY_RUN_COMPLETE, "error")
            raise HTTPException(status_code=404, detail="Run not found")

        record_operation(OperationNames.MEMORY_RUN_COMPLETE, "success")
        return _run_to_response(run)
    except HTTPException:
        raise
    except Exception:
        record_operation(OperationNames.MEMORY_RUN_COMPLETE, "error")
        raise


@router.post("/playbook/agent", response_model=PlaybookResponse)
async def get_playbook_for_agent(
    body: AgentPlaybookRequest,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    Get playbook entries filtered by agent_id and optional task_type.

    ACE Loop: Before starting a task, query agent-specific strategies
    and reflections that have been validated by past runs.
    """
    start = time.monotonic()
    embed_service = get_embedding_service()

    query_embedding = await embed_service.embed_single(body.query, db)

    results = await ACERepository.get_playbook_for_agent(
        db,
        query_embedding=query_embedding,
        project_id=project_id,
        agent_id=body.agent_id,
        namespace=body.namespace,
        task_type=body.task_type,
        top_k=body.top_k,
        min_effectiveness=body.min_effectiveness,
    )

    elapsed_ms = (time.monotonic() - start) * 1000

    await _emit_event(
        db,
        project_id=project_id,
        namespace=body.namespace,
        agent_id=body.agent_id,
        event_type=MemoryEventType.QUERIED.value,
        payload={
            "source": "playbook_agent",
            "query": body.query,
            "task_type": body.task_type,
            "result_count": len(results),
        },
    )

    entries = [
        PlaybookEntry(
            id=mem.id,
            content=mem.content,
            memory_type=mem.memory_type,
            effectiveness_score=mem.get_effectiveness_score(),
            bullet_helpful=mem.bullet_helpful,
            bullet_harmful=mem.bullet_harmful,
            error_pattern=mem.error_pattern,
            created_at=mem.created_at,
        )
        for mem, score in results
    ]

    return PlaybookResponse(
        entries=entries,
        query_time_ms=round(elapsed_ms, 2),
    )


@router.post("/curate", response_model=CurationResponse)
async def curate(
    body: CurateRequest,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger a curation cycle.

    ACE Loop: The Curation phase. Identifies:
    - Promoted: high-effectiveness entries validated by runs
    - Flagged: low-effectiveness entries for deprecation
    - Consolidation candidates: similar entries that could be merged
    """
    try:
        with track_latency(OperationNames.MEMORY_CURATE):
            result = await ACERepository.curate(
                db,
                project_id=project_id,
                namespace=body.namespace,
                agent_id=body.agent_id,
                top_k=body.top_k,
                min_effectiveness_threshold=body.min_effectiveness_threshold,
            )

        record_operation(OperationNames.MEMORY_CURATE, "success")

        return CurationResponse(
            promoted=[CurationEntryResponse(**e) for e in result["promoted"]],
            flagged=[CurationEntryResponse(**e) for e in result["flagged"]],
            consolidation_candidates=[
                ConsolidationCandidate(**c) for c in result["consolidation_candidates"]
            ],
        )
    except Exception:
        record_operation(OperationNames.MEMORY_CURATE, "error")
        raise


def _run_to_response(run) -> RunResponse:
    """Convert AceRun model to response."""
    return RunResponse(
        run_id=run.run_id,
        agent_id=run.agent_id,
        task_type=run.task_type,
        namespace=run.namespace,
        status=run.status,
        success=run.success,
        evaluation=run.evaluation or {},
        logs=run.logs or {},
        memory_ids_used=run.memory_ids_used or [],
        reflection_ids=run.reflection_ids or [],
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


# ---------- Session Progress Routes ----------

@router.post("/session", response_model=SessionProgressResponse)
async def create_session(
    body: SessionProgressCreate,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new session for progress tracking.

    Anthropic Pattern: claude-progress.txt enables agents to quickly
    understand state when starting with fresh context. This is the
    structured, queryable version.
    """
    try:
        with track_latency(OperationNames.MEMORY_SESSION_CREATE):
            session = await ACERepository.create_session(
                db,
                project_id=project_id,
                session_id=body.session_id,
                agent_id=body.agent_id,
                user_id=body.user_id,
                namespace=body.namespace,
            )
        record_operation(OperationNames.MEMORY_SESSION_CREATE, "success")
        return _session_to_response(session)
    except Exception:
        record_operation(OperationNames.MEMORY_SESSION_CREATE, "error")
        raise


@router.get("/session/{session_id}", response_model=SessionProgressResponse)
async def get_session(
    session_id: str,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    """Get session progress by session_id."""
    try:
        with track_latency(OperationNames.MEMORY_SESSION_GET):
            session = await ACERepository.get_session(db, session_id, project_id)

        if not session:
            record_operation(OperationNames.MEMORY_SESSION_GET, "error")
            raise HTTPException(status_code=404, detail="Session not found")

        record_operation(OperationNames.MEMORY_SESSION_GET, "success")
        return _session_to_response(session)
    except HTTPException:
        raise
    except Exception:
        record_operation(OperationNames.MEMORY_SESSION_GET, "error")
        raise


@router.patch("/session/{session_id}", response_model=SessionProgressResponse)
async def update_session(
    session_id: str,
    body: SessionProgressUpdate,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    Update session progress.

    This is how agents record their progress:
    - Mark items complete
    - Set current work item
    - Queue next items
    - Record blockers
    """
    try:
        with track_latency(OperationNames.MEMORY_SESSION_UPDATE):
            session = await ACERepository.update_session(
                db,
                session_id=session_id,
                project_id=project_id,
                completed_items=body.completed_items,
                in_progress_item=body.in_progress_item,
                next_items=body.next_items,
                blocked_items=body.blocked_items,
                summary=body.summary,
                last_action=body.last_action,
                status=body.status,
                total_items=body.total_items,
            )

        if not session:
            record_operation(OperationNames.MEMORY_SESSION_UPDATE, "error")
            raise HTTPException(status_code=404, detail="Session not found")

        record_operation(OperationNames.MEMORY_SESSION_UPDATE, "success")
        return _session_to_response(session)
    except HTTPException:
        raise
    except Exception:
        record_operation(OperationNames.MEMORY_SESSION_UPDATE, "error")
        raise


def _session_to_response(session) -> SessionProgressResponse:
    """Convert session model to response."""
    completed = session.completed_items or []
    total = session.total_items or len(completed)
    progress = (len(completed) / total * 100) if total > 0 else 0

    return SessionProgressResponse(
        id=session.id,
        session_id=session.session_id,
        status=session.status,
        completed_count=len(completed),
        total_items=total,
        progress_percent=round(progress, 1),
        completed_items=completed,
        in_progress_item=session.in_progress_item,
        next_items=session.next_items or [],
        blocked_items=session.blocked_items or [],
        summary=session.summary,
        last_action=session.last_action,
        updated_at=session.updated_at,
    )


# ---------- Feature Tracking Routes ----------

@router.post("/feature", response_model=FeatureResponse)
async def create_feature(
    body: FeatureCreate,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a feature to track.

    Anthropic Pattern: Feature lists with pass/fail status prevent
    agents from declaring victory prematurely. Each feature must be
    explicitly verified before marking complete.
    """
    try:
        with track_latency(OperationNames.MEMORY_FEATURE_CREATE):
            feature = await ACERepository.create_feature(
                db,
                project_id=project_id,
                feature_id=body.feature_id,
                description=body.description,
                session_id=body.session_id,
                namespace=body.namespace,
                category=body.category,
                test_steps=body.test_steps,
            )
        record_operation(OperationNames.MEMORY_FEATURE_CREATE, "success")
        return _feature_to_response(feature)
    except Exception:
        record_operation(OperationNames.MEMORY_FEATURE_CREATE, "error")
        raise


@router.get("/feature/{feature_id}", response_model=FeatureResponse)
async def get_feature(
    feature_id: str,
    namespace: str = "default",
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    """Get feature by feature_id."""
    try:
        with track_latency(OperationNames.MEMORY_FEATURE_GET):
            feature = await ACERepository.get_feature(
                db, feature_id, project_id, namespace
            )

        if not feature:
            record_operation(OperationNames.MEMORY_FEATURE_GET, "error")
            raise HTTPException(status_code=404, detail="Feature not found")

        record_operation(OperationNames.MEMORY_FEATURE_GET, "success")
        return _feature_to_response(feature)
    except HTTPException:
        raise
    except Exception:
        record_operation(OperationNames.MEMORY_FEATURE_GET, "error")
        raise


@router.patch("/feature/{feature_id}", response_model=FeatureResponse)
async def update_feature(
    feature_id: str,
    body: FeatureUpdate,
    namespace: str = "default",
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """
    Update feature status.

    Only mark passes=true after proper verification!
    """
    try:
        with track_latency(OperationNames.MEMORY_FEATURE_UPDATE):
            feature = await ACERepository.update_feature(
                db,
                feature_id=feature_id,
                project_id=project_id,
                namespace=namespace,
                status=body.status,
                passes=body.passes,
                implemented_by=body.implemented_by,
                verified_by=body.verified_by,
                implementation_notes=body.implementation_notes,
                failure_reason=body.failure_reason,
                task_id=body.task_id,
                retrieval_event_id=body.retrieval_event_id,
                selected_memory_ids=body.selected_memory_ids,
            )

        if not feature:
            record_operation(OperationNames.MEMORY_FEATURE_UPDATE, "error")
            raise HTTPException(status_code=404, detail="Feature not found")

        record_operation(OperationNames.MEMORY_FEATURE_UPDATE, "success")
        return _feature_to_response(feature)
    except HTTPException:
        raise
    except Exception:
        record_operation(OperationNames.MEMORY_FEATURE_UPDATE, "error")
        raise


@router.get("/features", response_model=FeatureListResponse)
async def list_features(
    namespace: str = "default",
    session_id: str | None = None,
    status: str | None = None,
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    """
    List all features with status summary.

    Use this at the start of a session to see what's complete
    and what still needs work.
    """
    try:
        with track_latency(OperationNames.MEMORY_FEATURE_LIST):
            features = await ACERepository.list_features(
                db,
                project_id=project_id,
                namespace=namespace,
                session_id=session_id,
                status=status,
            )

        total = len(features)
        passing = sum(1 for f in features if f.passes)
        failing = sum(1 for f in features if f.status == FeatureStatus.FAILED.value)
        in_progress = sum(1 for f in features if f.status == FeatureStatus.IN_PROGRESS.value)

        record_operation(OperationNames.MEMORY_FEATURE_LIST, "success")
        return FeatureListResponse(
            features=[_feature_to_response(f) for f in features],
            total=total,
            passing=passing,
            failing=failing,
            in_progress=in_progress,
        )
    except Exception:
        record_operation(OperationNames.MEMORY_FEATURE_LIST, "error")
        raise


def _feature_to_response(feature) -> FeatureResponse:
    """Convert feature model to response."""
    return FeatureResponse(
        id=feature.id,
        feature_id=feature.feature_id,
        description=feature.description,
        category=feature.category,
        status=feature.status,
        passes=feature.passes,
        test_steps=feature.test_steps or [],
        implemented_by=feature.implemented_by,
        verified_by=feature.verified_by,
        updated_at=feature.updated_at,
    )


# ---------- Evaluation Harness Routes ----------

@router.get("/eval/metrics", response_model=EvalMetricsResponse)
async def get_evaluation_metrics(
    namespace: str | None = None,
    agent_id: str | None = None,
    window: str = "global",
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    """
    Get aggregated evaluation metrics for the confidence harness.

    Supported windows: 24h, 7d, 30d, global
    """
    if window not in ["24h", "7d", "30d", "global"]:
        raise HTTPException(status_code=400, detail="Invalid window. Use 24h, 7d, 30d, or global.")

    metrics = await EvalRepository.get_metrics(
        db,
        project_id=project_id,
        namespace=namespace,
        agent_id=agent_id,
        window=window
    )
    return EvalMetricsResponse(**metrics)


@router.get("/eval/correlation", response_model=EvalCorrelationResponse)
async def get_vote_utility_correlation(
    namespace: str | None = None,
    agent_id: str | None = None,
    window: str = "global",
    project_id: str = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_read_db),
):
    """
    Calculate correlation between memory votes and actual task success.

    This answers the research question: 'Do votes predict actual usefulness?'
    """
    correlation = await EvalRepository.get_vote_utility_correlation(
        db,
        project_id=project_id,
        namespace=namespace,
        agent_id=agent_id,
        window=window
    )
    return EvalCorrelationResponse(**correlation)
