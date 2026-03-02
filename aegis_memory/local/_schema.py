"""
SQLite schema for Aegis Memory local mode.

Mirrors server/models.py with adaptations for SQLite:
- No pgvector: embeddings stored as BLOB (numpy .tobytes())
- No project_id: single-tenant local mode
- JSON columns stored as TEXT
- schema_version table for future migrations
"""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

DDL = """
-- Schema versioning
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Core memory table
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    agent_id TEXT,
    namespace TEXT NOT NULL DEFAULT 'default',
    memory_type TEXT NOT NULL DEFAULT 'standard',
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    embedding BLOB,
    metadata TEXT NOT NULL DEFAULT '{}',
    scope TEXT NOT NULL DEFAULT 'agent-private',
    shared_with_agents TEXT NOT NULL DEFAULT '[]',
    derived_from_agents TEXT NOT NULL DEFAULT '[]',
    coordination_metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT,
    bullet_helpful INTEGER NOT NULL DEFAULT 0,
    bullet_harmful INTEGER NOT NULL DEFAULT 0,
    is_deprecated INTEGER NOT NULL DEFAULT 0,
    deprecated_at TEXT,
    deprecated_by TEXT,
    superseded_by TEXT,
    source_trajectory_id TEXT,
    error_pattern TEXT,
    session_id TEXT,
    entity_id TEXT,
    sequence_number INTEGER,
    last_accessed_at TEXT,
    access_count INTEGER NOT NULL DEFAULT 0,
    integrity_hash TEXT,
    content_flags TEXT NOT NULL DEFAULT '[]',
    trust_level TEXT NOT NULL DEFAULT 'internal'
);

CREATE INDEX IF NOT EXISTS ix_memories_content_hash ON memories(content_hash);
CREATE INDEX IF NOT EXISTS ix_memories_ns_user ON memories(namespace, user_id);
CREATE INDEX IF NOT EXISTS ix_memories_ns_scope ON memories(namespace, scope);
CREATE INDEX IF NOT EXISTS ix_memories_ns_agent ON memories(namespace, agent_id);
CREATE INDEX IF NOT EXISTS ix_memories_ns_type ON memories(namespace, memory_type);
CREATE INDEX IF NOT EXISTS ix_memories_active ON memories(namespace, is_deprecated)
    WHERE is_deprecated = 0;

-- Vote history
CREATE TABLE IF NOT EXISTS vote_history (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    voter_agent_id TEXT NOT NULL,
    vote TEXT NOT NULL,
    context TEXT,
    task_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS ix_votes_memory ON vote_history(memory_id);

-- Session progress
CREATE TABLE IF NOT EXISTS session_progress (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL UNIQUE,
    agent_id TEXT,
    user_id TEXT,
    namespace TEXT NOT NULL DEFAULT 'default',
    completed_items TEXT NOT NULL DEFAULT '[]',
    in_progress_item TEXT,
    next_items TEXT NOT NULL DEFAULT '[]',
    blocked_items TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    summary TEXT,
    last_action TEXT,
    total_items INTEGER NOT NULL DEFAULT 0,
    completed_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Feature tracker
CREATE TABLE IF NOT EXISTS feature_tracker (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    namespace TEXT NOT NULL DEFAULT 'default',
    feature_id TEXT NOT NULL,
    category TEXT,
    description TEXT NOT NULL,
    test_steps TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'not_started',
    passes INTEGER NOT NULL DEFAULT 0,
    implemented_by TEXT,
    verified_by TEXT,
    implementation_notes TEXT,
    failure_reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_feature_unique
    ON feature_tracker(namespace, feature_id);

-- ACE runs
CREATE TABLE IF NOT EXISTS ace_runs (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    agent_id TEXT,
    task_type TEXT,
    namespace TEXT NOT NULL DEFAULT 'default',
    status TEXT NOT NULL DEFAULT 'running',
    success INTEGER,
    evaluation TEXT NOT NULL DEFAULT '{}',
    logs TEXT NOT NULL DEFAULT '{}',
    memory_ids_used TEXT NOT NULL DEFAULT '[]',
    reflection_ids TEXT NOT NULL DEFAULT '[]',
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Interaction events
CREATE TABLE IF NOT EXISTS interaction_events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    agent_id TEXT,
    content TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    tool_calls TEXT NOT NULL DEFAULT '[]',
    parent_event_id TEXT REFERENCES interaction_events(event_id) ON DELETE SET NULL,
    namespace TEXT NOT NULL DEFAULT 'default',
    extra_metadata TEXT,
    embedding BLOB
);

CREATE INDEX IF NOT EXISTS ix_interaction_session_ts
    ON interaction_events(session_id, timestamp);
CREATE INDEX IF NOT EXISTS ix_interaction_agent_ts
    ON interaction_events(agent_id, timestamp);
CREATE INDEX IF NOT EXISTS ix_interaction_parent
    ON interaction_events(parent_event_id)
    WHERE parent_event_id IS NOT NULL;

-- Embedding cache
CREATE TABLE IF NOT EXISTS embedding_cache (
    content_hash TEXT PRIMARY KEY,
    embedding BLOB NOT NULL,
    model TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    hit_count INTEGER NOT NULL DEFAULT 0
);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create all tables if they don't exist and record schema version."""
    conn.executescript(DDL)

    row = conn.execute(
        "SELECT MAX(version) FROM schema_version"
    ).fetchone()
    current = row[0] if row and row[0] is not None else 0

    if current < SCHEMA_VERSION:
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
        conn.commit()


def migrate_if_needed(conn: sqlite3.Connection) -> None:
    """Run any pending migrations. Currently a no-op at v1."""
    row = conn.execute(
        "SELECT MAX(version) FROM schema_version"
    ).fetchone()
    current = row[0] if row and row[0] is not None else 0

    if current < SCHEMA_VERSION:
        ensure_schema(conn)
