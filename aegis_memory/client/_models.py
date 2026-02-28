"""Aegis SDK data models (dataclasses)."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class Memory:
    """A memory from Aegis."""
    id: str
    content: str
    user_id: Optional[str]
    agent_id: Optional[str]
    namespace: str
    metadata: Dict[str, Any]
    created_at: datetime
    scope: str
    shared_with_agents: List[str]
    derived_from_agents: List[str]
    coordination_metadata: Dict[str, Any]
    score: Optional[float] = None
    memory_type: str = "standard"
    bullet_helpful: int = 0
    bullet_harmful: int = 0
    content_flags: List[str] = field(default_factory=list)
    trust_level: str = "internal"
    integrity_valid: Optional[bool] = None


@dataclass
class ContentScanResult:
    """Result of a content security scan (dry-run)."""
    allowed: bool
    action: str
    flags: List[str]
    detections: List[Dict[str, Any]]


@dataclass
class SecurityAuditEvent:
    """A security audit event from the audit trail."""
    event_id: str
    event_type: str
    project_id: str
    agent_id: Optional[str]
    memory_id: Optional[str]
    details: Dict[str, Any]
    created_at: str


@dataclass
class IntegrityCheckResult:
    """Result of memory integrity verification."""
    memory_id: str
    integrity_valid: bool
    has_hash: bool
    detail: str


@dataclass
class AddResult:
    """Result of adding a memory."""
    id: str
    deduped_from: Optional[str] = None
    inferred_scope: Optional[str] = None


@dataclass
class VoteResult:
    """Result of voting on a memory."""
    memory_id: str
    bullet_helpful: int
    bullet_harmful: int
    effectiveness_score: float


@dataclass
class DeltaResultItem:
    """Result of a single delta operation."""
    operation: str
    success: bool
    memory_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class DeltaResult:
    """Result of applying delta updates."""
    results: List[DeltaResultItem]
    total_time_ms: float


@dataclass
class PlaybookEntry:
    """An entry from the playbook (strategy or reflection)."""
    id: str
    content: str
    memory_type: str
    effectiveness_score: float
    bullet_helpful: int
    bullet_harmful: int
    error_pattern: Optional[str]
    created_at: datetime


@dataclass
class PlaybookResult:
    """Result of playbook query."""
    entries: List[PlaybookEntry]
    query_time_ms: float


@dataclass
class SessionProgress:
    """Session progress tracking."""
    id: str
    session_id: str
    status: str
    completed_count: int
    total_items: int
    progress_percent: float
    completed_items: List[str]
    in_progress_item: Optional[str]
    next_items: List[str]
    blocked_items: List[Dict]
    summary: Optional[str]
    last_action: Optional[str]
    updated_at: datetime


@dataclass
class Feature:
    """Feature tracking."""
    id: str
    feature_id: str
    description: str
    category: Optional[str]
    status: str
    passes: bool
    test_steps: List[str]
    implemented_by: Optional[str]
    verified_by: Optional[str]
    updated_at: datetime


@dataclass
class FeatureList:
    """List of features with summary."""
    features: List[Feature]
    total: int
    passing: int
    failing: int
    in_progress: int


@dataclass
class HandoffBaton:
    """Handoff baton for agent-to-agent state transfer."""
    source_agent_id: str
    target_agent_id: str
    namespace: str
    user_id: Optional[str]
    task_context: Optional[str]
    summary: Optional[str]
    active_tasks: List[str]
    blocked_on: List[str]
    recent_decisions: List[str]
    key_facts: List[str]
    memory_ids: List[str]


@dataclass
class RunResult:
    """Result of an ACE run operation."""
    run_id: str
    status: str
    success: Optional[bool]
    agent_id: Optional[str]
    task_type: Optional[str]
    namespace: str
    evaluation: Dict[str, Any]
    logs: Dict[str, Any]
    memory_ids_used: List[str]
    reflection_ids: List[str]
    started_at: datetime
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


@dataclass
class CurationEntry:
    """A memory entry in curation results."""
    id: str
    content: str
    memory_type: str
    effectiveness_score: float
    bullet_helpful: int
    bullet_harmful: int
    total_votes: int


@dataclass
class ConsolidationCandidate:
    """A pair of similar memories that could be consolidated."""
    memory_id_a: str
    memory_id_b: str
    content_a: str
    content_b: str
    reason: str


@dataclass
class CurationResult:
    """Result of a curation cycle."""
    promoted: List[CurationEntry]
    flagged: List[CurationEntry]
    consolidation_candidates: List[ConsolidationCandidate]


@dataclass
class InteractionEvent:
    """A recorded interaction event."""
    event_id: str
    project_id: str
    session_id: str
    agent_id: Optional[str]
    content: Optional[str]
    timestamp: datetime
    tool_calls: List[Any]
    parent_event_id: Optional[str]
    namespace: str
    extra_metadata: Optional[Dict[str, Any]]
    has_embedding: bool


@dataclass
class InteractionEventResult:
    """Result of creating an interaction event."""
    event_id: str
    session_id: str
    namespace: str
    has_embedding: bool


@dataclass
class SessionTimelineResult:
    """Timeline of events for a session."""
    session_id: str
    namespace: str
    events: List[InteractionEvent]
    count: int


@dataclass
class AgentInteractionsResult:
    """Interaction history for an agent."""
    agent_id: str
    namespace: str
    events: List[InteractionEvent]
    count: int


@dataclass
class InteractionSearchResultItem:
    """A single search result with score."""
    event: InteractionEvent
    score: float


@dataclass
class InteractionSearchResult:
    """Result of a semantic search over interaction events."""
    results: List[InteractionSearchResultItem]
    query_time_ms: float


@dataclass
class EventWithChainResult:
    """An event plus its full causal chain (root -> leaf)."""
    event: InteractionEvent
    chain: List[InteractionEvent]
    chain_depth: int
