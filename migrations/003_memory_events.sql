-- Aegis Memory Events Timeline Migration
-- Version: 1.2.0
-- Description: Adds memory_events table for timeline/audit events

CREATE TABLE IF NOT EXISTS memory_events (
    event_id VARCHAR(32) PRIMARY KEY,
    memory_id VARCHAR(32) REFERENCES memories(id) ON DELETE CASCADE,
    project_id VARCHAR(64) NOT NULL,
    namespace VARCHAR(64) NOT NULL DEFAULT 'default',
    agent_id VARCHAR(64),
    event_type VARCHAR(32) NOT NULL CHECK (
        event_type IN (
            'created',
            'queried',
            'voted_helpful',
            'voted_harmful',
            'deprecated',
            'delta_updated',
            'reflected'
        )
    ),
    event_payload JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_memory_events_project_created
    ON memory_events (project_id, created_at);

CREATE INDEX IF NOT EXISTS ix_memory_events_memory_created
    ON memory_events (memory_id, created_at);
