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


class FeatureStatus(str, Enum):
    """Feature tracking status for long-running agent tasks."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    TESTING = "testing"
    COMPLETE = "complete"
    FAILED = "failed"


class MemoryEventType(str, Enum):
    CREATED = "created"
    QUERIED = "queried"
    VOTED_HELPFUL = "voted_helpful"
    VOTED_HARMFUL = "voted_harmful"
    DEPRECATED = "deprecated"
    DELTA_UPDATED = "delta_updated"
    REFLECTED = "reflected"


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
    memory_type = Column(String(16), nullable=False, default=MemoryType.STANDARD.value)

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

    # Relationships
    votes = relationship("VoteHistory", back_populates="memory", cascade="all, delete-orphan")

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
    event_payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index('ix_memory_events_project_created', 'project_id', 'created_at'),
        Index('ix_memory_events_memory_created', 'memory_id', 'created_at'),
    )


# SQL to run after table creation (for pgvector setup)
INIT_SQL = """
-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Set HNSW search parameters for queries (can tune per-query too)
SET hnsw.ef_search = 100;

-- Create the HNSW index if it doesn't exist
-- This is idempotent
CREATE INDEX IF NOT EXISTS ix_memories_embedding_hnsw
ON memories USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- ACE Enhancement: Index for memory type queries
CREATE INDEX IF NOT EXISTS ix_memories_project_type
ON memories (project_id, namespace, memory_type);

-- ACE Enhancement: Partial index for active (non-deprecated) memories
CREATE INDEX IF NOT EXISTS ix_memories_active
ON memories (project_id, namespace)
WHERE is_deprecated = false;

-- ACE Enhancement: Vote history indexes
CREATE INDEX IF NOT EXISTS ix_votes_memory ON vote_history (memory_id);
CREATE INDEX IF NOT EXISTS ix_votes_agent ON vote_history (project_id, voter_agent_id);

-- ACE Enhancement: Session progress indexes
CREATE INDEX IF NOT EXISTS ix_session_project ON session_progress (project_id, namespace);
CREATE INDEX IF NOT EXISTS ix_session_agent ON session_progress (project_id, agent_id);

-- ACE Enhancement: Feature tracker indexes
CREATE INDEX IF NOT EXISTS ix_feature_project ON feature_tracker (project_id, namespace);
CREATE INDEX IF NOT EXISTS ix_feature_session ON feature_tracker (session_id);
CREATE INDEX IF NOT EXISTS ix_feature_status ON feature_tracker (project_id, status);
"""


# Migration SQL for existing deployments
MIGRATION_SQL_V1_1 = """
-- Add new columns to memories table (ACE enhancements)
ALTER TABLE memories ADD COLUMN IF NOT EXISTS memory_type VARCHAR(16) DEFAULT 'standard';
ALTER TABLE memories ADD COLUMN IF NOT EXISTS is_deprecated BOOLEAN DEFAULT false;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS deprecated_at TIMESTAMPTZ;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS deprecated_by VARCHAR(64);
ALTER TABLE memories ADD COLUMN IF NOT EXISTS superseded_by VARCHAR(32);
ALTER TABLE memories ADD COLUMN IF NOT EXISTS source_trajectory_id VARCHAR(64);
ALTER TABLE memories ADD COLUMN IF NOT EXISTS error_pattern VARCHAR(128);

-- Create vote_history table
CREATE TABLE IF NOT EXISTS vote_history (
    id VARCHAR(32) PRIMARY KEY,
    memory_id VARCHAR(32) REFERENCES memories(id) ON DELETE CASCADE,
    project_id VARCHAR(64) NOT NULL,
    voter_agent_id VARCHAR(64) NOT NULL,
    vote VARCHAR(8) NOT NULL,
    context TEXT,
    task_id VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create session_progress table
CREATE TABLE IF NOT EXISTS session_progress (
    id VARCHAR(32) PRIMARY KEY,
    project_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) UNIQUE NOT NULL,
    agent_id VARCHAR(64),
    user_id VARCHAR(64),
    namespace VARCHAR(64) DEFAULT 'default',
    completed_items JSONB DEFAULT '[]',
    in_progress_item VARCHAR(256),
    next_items JSONB DEFAULT '[]',
    blocked_items JSONB DEFAULT '[]',
    status VARCHAR(16) DEFAULT 'active',
    summary TEXT,
    last_action TEXT,
    total_items INTEGER DEFAULT 0,
    completed_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create feature_tracker table
CREATE TABLE IF NOT EXISTS feature_tracker (
    id VARCHAR(32) PRIMARY KEY,
    project_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64),
    namespace VARCHAR(64) DEFAULT 'default',
    feature_id VARCHAR(128) NOT NULL,
    category VARCHAR(64),
    description TEXT NOT NULL,
    test_steps JSONB DEFAULT '[]',
    status VARCHAR(16) DEFAULT 'not_started',
    passes BOOLEAN DEFAULT false,
    implemented_by VARCHAR(64),
    verified_by VARCHAR(64),
    implementation_notes TEXT,
    failure_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- Create indexes
CREATE INDEX IF NOT EXISTS ix_memories_project_type ON memories (project_id, namespace, memory_type);
CREATE INDEX IF NOT EXISTS ix_memories_active ON memories (project_id, namespace) WHERE is_deprecated = false;
CREATE INDEX IF NOT EXISTS ix_votes_memory ON vote_history (memory_id);
CREATE INDEX IF NOT EXISTS ix_votes_agent ON vote_history (project_id, voter_agent_id);
CREATE INDEX IF NOT EXISTS ix_session_project ON session_progress (project_id, namespace);
CREATE INDEX IF NOT EXISTS ix_session_agent ON session_progress (project_id, agent_id);
CREATE INDEX IF NOT EXISTS ix_feature_project ON feature_tracker (project_id, namespace);
CREATE INDEX IF NOT EXISTS ix_feature_session ON feature_tracker (session_id);
CREATE INDEX IF NOT EXISTS ix_feature_status ON feature_tracker (project_id, status);
"""
