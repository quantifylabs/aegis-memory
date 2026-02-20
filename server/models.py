"""
Aegis Production Models - Scalable Multi-Agent Memory Layer

Key changes from v0:
1. HNSW index on embeddings for O(log n) vector search
2. Proper composite indexes for multi-tenant queries
3. Async-ready with SQLAlchemy 2.0 patterns
4. Partitioning-ready schema design

ACE-Inspired Enhancements (v1.1):
5. Memory types: standard, reflection, progress, feature
6. Voting system with history tracking
7. Delta updates support
8. Session progress tracking
"""

from enum import Enum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class MemoryScope(str, Enum):
    AGENT_PRIVATE = "agent-private"
    AGENT_SHARED = "agent-shared"
    GLOBAL = "global"


class MemoryType(str, Enum):
    """
    Memory types inspired by ACE paper patterns.

    STANDARD: Regular memories (facts, preferences, context)
    REFLECTION: Insights extracted from successes/failures (ACE Reflector output)
    PROGRESS: Session progress tracking (Anthropic's claude-progress.txt pattern)
    FEATURE: Feature status tracking (prevents premature victory declaration)
    STRATEGY: Reusable strategies and patterns (ACE playbook entries)
    """
    STANDARD = "standard"
    REFLECTION = "reflection"
    PROGRESS = "progress"
    FEATURE = "feature"
    STRATEGY = "strategy"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    CONTROL = "control"


class FeatureStatus(str, Enum):
    """Feature tracking status for long-running agent tasks."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    TESTING = "testing"
    COMPLETE = "complete"
    FAILED = "failed"


class Project(Base):
    """
    Project represents a tenant in the multi-tenant auth model.

    Each project has its own set of API keys and isolated memory namespace.
    """
    __tablename__ = "projects"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    api_keys = relationship("ApiKey", back_populates="project", cascade="all, delete-orphan")


class ApiKey(Base):
    """
    API key for project-scoped authentication.

    Keys are stored as SHA-256 hashes. The raw key is only shown once at creation.
    """
    __tablename__ = "api_keys"

    id = Column(String(32), primary_key=True)
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    name = Column(String(128), nullable=False, default="default")
    is_active = Column(Boolean, nullable=False, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    project = relationship("Project", back_populates="api_keys")

    __table_args__ = (
        Index('ix_api_keys_project', 'project_id'),
    )


class MemoryEventType(str, Enum):
    CREATED = "created"
    QUERIED = "queried"
    VOTED_HELPFUL = "voted_helpful"
    VOTED_HARMFUL = "voted_harmful"
    DEPRECATED = "deprecated"
    DELTA_UPDATED = "delta_updated"
    REFLECTED = "reflected"
    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    CURATED = "curated"


class Memory(Base):
    """
    Production memory table with proper indexing strategy.

    Index Strategy:
    - HNSW index on embedding for fast ANN search (critical!)
    - Composite B-tree indexes for filtering BEFORE vector search
    - Partial indexes for common access patterns

    ACE Enhancements:
    - memory_type: Categorizes memories (standard, reflection, progress, feature, strategy)
    - bullet_helpful/bullet_harmful: Vote tracking for self-improvement
    - is_deprecated: Soft delete for preserving history while marking outdated
    """
    __tablename__ = "memories"

    id = Column(String(32), primary_key=True)
    project_id = Column(String(64), nullable=False)
    user_id = Column(String(64), nullable=True)
    agent_id = Column(String(64), nullable=True)
    namespace = Column(String(64), nullable=False, default="default")

    # ACE Enhancement: Memory type categorization
    memory_type = Column(String(32), nullable=False, default=MemoryType.STANDARD.value)

    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)  # For fast dedup

    embedding = Column(Vector(1536), nullable=False)

    metadata_json = Column("metadata", JSON, nullable=False, default=dict)

    scope = Column(String(16), nullable=False, default=MemoryScope.AGENT_PRIVATE.value)
    shared_with_agents = Column(JSON, nullable=False, default=list)
    derived_from_agents = Column(JSON, nullable=False, default=list)
    coordination_metadata = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Pre-computed expiration

    # ACE Enhancement: Vote tracking for self-improvement
    bullet_helpful = Column(Integer, nullable=False, default=0)
    bullet_harmful = Column(Integer, nullable=False, default=0)

    # ACE Enhancement: Soft deprecation (preserves history, marks outdated)
    is_deprecated = Column(Boolean, nullable=False, default=False)
    deprecated_at = Column(DateTime(timezone=True), nullable=True)
    deprecated_by = Column(String(64), nullable=True)  # agent_id that deprecated it
    superseded_by = Column(String(32), nullable=True)  # ID of replacement memory

    # ACE Enhancement: Source tracking for reflections
    source_trajectory_id = Column(String(64), nullable=True)  # Links reflection to source
    error_pattern = Column(String(128), nullable=True)  # Categorizes error type

    # Typed Memory (v1.9.0): Cognitive memory type support
    session_id = Column(String(64), nullable=True)  # Links episodic memories to session
    entity_id = Column(String(128), nullable=True)  # Links semantic memories to entity
    sequence_number = Column(Integer, nullable=True)  # Ordering within session

    # Relationships
    votes = relationship("VoteHistory", back_populates="memory", cascade="all, delete-orphan")
    shared_agents = relationship("MemorySharedAgent", back_populates="memory", cascade="all, delete-orphan")

    # Composite indexes for the most common query patterns
    __table_args__ = (
        # Primary query pattern: project + namespace + user
        Index('ix_memories_project_ns_user', 'project_id', 'namespace', 'user_id'),

        # Cross-agent queries: project + namespace + scope
        Index('ix_memories_project_ns_scope', 'project_id', 'namespace', 'scope'),

        # Agent-specific queries
        Index('ix_memories_project_agent', 'project_id', 'agent_id'),

        # TTL cleanup (partial index for non-null expires_at)
        Index('ix_memories_expires', 'expires_at', postgresql_where=text('expires_at IS NOT NULL')),

        # ACE Enhancement: Memory type queries
        Index('ix_memories_project_type', 'project_id', 'namespace', 'memory_type'),

        # ACE Enhancement: Non-deprecated memories (most common query)
        Index('ix_memories_active', 'project_id', 'namespace', 'is_deprecated',
              postgresql_where=text('is_deprecated = false')),

        # HNSW index for vector similarity search - THIS IS CRITICAL
        # lists=100 is good for 100k-1M vectors, increase for larger datasets
        Index(
            'ix_memories_embedding_hnsw',
            'embedding',
            postgresql_using='hnsw',
            postgresql_with={'m': 16, 'ef_construction': 64},
            postgresql_ops={'embedding': 'vector_cosine_ops'}
        ),

        # Typed Memory (v1.9.0): Partial indexes for session and entity queries
        Index('ix_memories_session', 'project_id', 'session_id',
              postgresql_where=text('session_id IS NOT NULL')),
        Index('ix_memories_entity', 'project_id', 'entity_id',
              postgresql_where=text('entity_id IS NOT NULL')),
    )

    def can_access(self, requesting_agent_id: str | None) -> bool:
        """Scope-aware access control."""
        if requesting_agent_id is None:
            return self.scope == MemoryScope.GLOBAL.value

        if self.scope == MemoryScope.GLOBAL.value:
            return True

        if self.scope == MemoryScope.AGENT_PRIVATE.value:
            return self.agent_id == requesting_agent_id

        if self.scope == MemoryScope.AGENT_SHARED.value:
            if self.agent_id == requesting_agent_id:
                return True
            shared = self.shared_with_agents or []
            return requesting_agent_id in shared

        return False

    def get_effectiveness_score(self) -> float:
        """
        Calculate memory effectiveness based on votes.
        Used for ranking and pruning decisions.

        Score = (helpful - harmful) / (helpful + harmful + 1)
        Range: -1.0 to 1.0
        """
        total = self.bullet_helpful + self.bullet_harmful
        if total == 0:
            return 0.0
        return (self.bullet_helpful - self.bullet_harmful) / (total + 1)


class MemorySharedAgent(Base):
    """
    Normalized join table for memory ACL sharing.

    Replaces JSON-based shared_with_agents lookups with an indexed table
    for O(1) ACL checks at scale.
    """
    __tablename__ = "memory_shared_agents"

    memory_id = Column(String(32), ForeignKey("memories.id", ondelete="CASCADE"), primary_key=True)
    shared_agent_id = Column(String(64), primary_key=True)
    project_id = Column(String(64), nullable=False)
    namespace = Column(String(64), nullable=False, default="default")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    memory = relationship("Memory", back_populates="shared_agents")

    __table_args__ = (
        Index('ix_msa_memory_agent', 'memory_id', 'shared_agent_id', unique=True),
        Index('ix_msa_query', 'project_id', 'namespace', 'shared_agent_id'),
    )


class VoteHistory(Base):
    """
    Track individual votes on memories for audit and analysis.

    ACE Insight: Understanding which agents find which memories
    helpful/harmful enables smarter memory curation.
    """
    __tablename__ = "vote_history"

    id = Column(String(32), primary_key=True)
    memory_id = Column(String(32), ForeignKey("memories.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(String(64), nullable=False)

    # Who voted
    voter_agent_id = Column(String(64), nullable=False)

    # The vote
    vote = Column(String(8), nullable=False)  # 'helpful' or 'harmful'

    # Context about when/why the vote was cast
    context = Column(Text, nullable=True)  # Optional explanation
    task_id = Column(String(64), nullable=True)  # What task was being performed

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    memory = relationship("Memory", back_populates="votes")

    __table_args__ = (
        Index('ix_votes_memory', 'memory_id'),
        Index('ix_votes_agent', 'project_id', 'voter_agent_id'),
    )


class SessionProgress(Base):
    """
    Track progress for long-running agent sessions.

    Inspired by Anthropic's claude-progress.txt pattern.
    Enables agents to quickly understand state when starting fresh context.
    """
    __tablename__ = "session_progress"

    id = Column(String(32), primary_key=True)
    project_id = Column(String(64), nullable=False)
    session_id = Column(String(64), nullable=False, unique=True)

    # Who owns this session
    agent_id = Column(String(64), nullable=True)
    user_id = Column(String(64), nullable=True)
    namespace = Column(String(64), nullable=False, default="default")

    # Progress tracking (JSON arrays)
    completed_items = Column(JSON, nullable=False, default=list)  # List of completed task/feature IDs
    in_progress_item = Column(String(256), nullable=True)  # Current work item
    next_items = Column(JSON, nullable=False, default=list)  # Prioritized queue
    blocked_items = Column(JSON, nullable=False, default=list)  # Blocked with reasons

    # Session state
    status = Column(String(16), nullable=False, default="active")  # active, paused, completed, failed

    # Human-readable summary (for quick context)
    summary = Column(Text, nullable=True)
    last_action = Column(Text, nullable=True)

    # Metrics
    total_items = Column(Integer, nullable=False, default=0)
    completed_count = Column(Integer, nullable=False, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('ix_session_project', 'project_id', 'namespace'),
        Index('ix_session_agent', 'project_id', 'agent_id'),
    )


class FeatureTracker(Base):
    """
    Track feature implementation status for complex projects.

    Prevents premature victory declaration (ACE/Anthropic insight).
    Each feature has explicit pass/fail status that must be verified.
    """
    __tablename__ = "feature_tracker"

    id = Column(String(32), primary_key=True)
    project_id = Column(String(64), nullable=False)
    session_id = Column(String(64), nullable=True)  # Optional link to session
    namespace = Column(String(64), nullable=False, default="default")

    # Feature definition
    feature_id = Column(String(128), nullable=False)
    category = Column(String(64), nullable=True)  # e.g., "functional", "ui", "api"
    description = Column(Text, nullable=False)

    # Verification steps (JSON array)
    test_steps = Column(JSON, nullable=False, default=list)

    # Status tracking
    status = Column(String(16), nullable=False, default=FeatureStatus.NOT_STARTED.value)
    passes = Column(Boolean, nullable=False, default=False)

    # Implementation details
    implemented_by = Column(String(64), nullable=True)  # agent_id
    verified_by = Column(String(64), nullable=True)  # agent_id that verified

    # Notes and context
    implementation_notes = Column(Text, nullable=True)
    failure_reason = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index('ix_feature_project', 'project_id', 'namespace'),
        Index('ix_feature_session', 'session_id'),
        Index('ix_feature_status', 'project_id', 'status'),
        # Unique constraint to prevent duplicate features in same namespace
        Index('ix_feature_unique', 'project_id', 'namespace', 'feature_id', unique=True),
    )


class EmbeddingCache(Base):
    """
    Cache embeddings to avoid redundant OpenAI calls.
    Hash the content, store the embedding.
    """
    __tablename__ = "embedding_cache"

    content_hash = Column(String(64), primary_key=True)
    embedding = Column(Vector(1536), nullable=False)
    model = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    hit_count = Column(Integer, nullable=False, default=0)


class MemoryEvent(Base):
    """Timeline events for memory operations and ACE workflows."""
    __tablename__ = "memory_events"

    event_id = Column(String(32), primary_key=True)
    memory_id = Column(String(32), ForeignKey("memories.id", ondelete="CASCADE"), nullable=True)
    project_id = Column(String(64), nullable=False)
    namespace = Column(String(64), nullable=False, default="default")
    agent_id = Column(String(64), nullable=True)
    event_type = Column(String(32), nullable=False)
    task_id = Column(String(128), nullable=True)
    retrieval_event_id = Column(String(32), nullable=True)
    selected_memory_ids = Column(JSON, nullable=False, default=list)
    event_payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index('ix_memory_events_project_created', 'project_id', 'created_at'),
        Index('ix_memory_events_memory_created', 'memory_id', 'created_at'),
        Index('ix_memory_events_project_task', 'project_id', 'task_id'),
        Index('ix_memory_events_project_retrieval', 'project_id', 'retrieval_event_id'),
    )


class AceRun(Base):
    """
    Track agent execution runs for ACE loop feedback.

    Links task execution to memories used, enabling:
    - Auto-voting: memories used in successful runs get 'helpful' votes
    - Auto-reflection: failures generate reflection memories
    - Run-playbook linking: playbook entries track which runs validated them
    """
    __tablename__ = "ace_runs"

    id = Column(String(32), primary_key=True)
    project_id = Column(String(64), nullable=False)
    run_id = Column(String(64), nullable=False)
    agent_id = Column(String(64), nullable=True)
    task_type = Column(String(64), nullable=True)
    namespace = Column(String(64), nullable=False, default="default")
    status = Column(String(16), nullable=False, default="running")
    success = Column(Boolean, nullable=True)
    evaluation = Column(JSON, nullable=False, default=dict)
    logs = Column(JSON, nullable=False, default=dict)
    memory_ids_used = Column(JSON, nullable=False, default=list)
    reflection_ids = Column(JSON, nullable=False, default=list)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('ix_ace_runs_project_run', 'project_id', 'run_id', unique=True),
        Index('ix_ace_runs_project_agent', 'project_id', 'agent_id'),
        Index('ix_ace_runs_project_task_type', 'project_id', 'task_type'),
    )


# Legacy SQL constants removed in v1.5.0 -- schema is now managed by Alembic.
# See alembic/versions/ for migration history.
