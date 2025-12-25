-- Aegis Memory ACE Tables Migration
-- Version: 1.1.0
-- Description: Adds ACE (Agentic Context Engineering) pattern support

-- =============================================================================
-- Extend memories table with ACE fields
-- =============================================================================

-- Add memory type column
ALTER TABLE memories ADD COLUMN IF NOT EXISTS memory_type VARCHAR(16) DEFAULT 'standard';

-- Add deprecation support
ALTER TABLE memories ADD COLUMN IF NOT EXISTS is_deprecated BOOLEAN DEFAULT false;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS deprecated_at TIMESTAMPTZ;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS superseded_by VARCHAR(32);
ALTER TABLE memories ADD COLUMN IF NOT EXISTS deprecation_reason TEXT;

-- Add voting counters
ALTER TABLE memories ADD COLUMN IF NOT EXISTS bullet_helpful INTEGER DEFAULT 0;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS bullet_harmful INTEGER DEFAULT 0;

-- Add reflection-specific fields
ALTER TABLE memories ADD COLUMN IF NOT EXISTS error_pattern VARCHAR(128);
ALTER TABLE memories ADD COLUMN IF NOT EXISTS correct_approach TEXT;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS applicable_contexts JSONB DEFAULT '[]';
ALTER TABLE memories ADD COLUMN IF NOT EXISTS source_trajectory_id VARCHAR(64);

-- Create index for memory type queries
CREATE INDEX IF NOT EXISTS ix_memories_type 
    ON memories (project_id, memory_type);

-- Create index for non-deprecated memories
CREATE INDEX IF NOT EXISTS ix_memories_active 
    ON memories (project_id, namespace, is_deprecated) 
    WHERE is_deprecated = false;

-- =============================================================================
-- Vote History Table
-- =============================================================================

CREATE TABLE IF NOT EXISTS vote_history (
    id VARCHAR(32) PRIMARY KEY,
    memory_id VARCHAR(32) NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    project_id VARCHAR(64) NOT NULL,
    voter_agent_id VARCHAR(64) NOT NULL,
    vote VARCHAR(8) NOT NULL CHECK (vote IN ('helpful', 'harmful')),
    context TEXT,
    task_id VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_votes_memory 
    ON vote_history (memory_id);

CREATE INDEX IF NOT EXISTS ix_votes_project_voter 
    ON vote_history (project_id, voter_agent_id);

COMMENT ON TABLE vote_history IS 'Tracks agent votes on memory usefulness for ACE playbook curation';

-- =============================================================================
-- Session Progress Table
-- =============================================================================

CREATE TABLE IF NOT EXISTS session_progress (
    id VARCHAR(32) PRIMARY KEY,
    project_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    agent_id VARCHAR(64),
    user_id VARCHAR(64),
    namespace VARCHAR(64) NOT NULL DEFAULT 'default',
    
    -- Progress tracking
    status VARCHAR(16) NOT NULL DEFAULT 'active' 
        CHECK (status IN ('active', 'paused', 'completed', 'failed')),
    total_items INTEGER DEFAULT 0,
    completed_items JSONB DEFAULT '[]',
    in_progress_item VARCHAR(256),
    next_items JSONB DEFAULT '[]',
    blocked_items JSONB DEFAULT '[]',
    
    -- Context
    summary TEXT,
    last_action TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Unique constraint per project/session
    CONSTRAINT uq_session_project UNIQUE (project_id, session_id)
);

CREATE INDEX IF NOT EXISTS ix_session_project 
    ON session_progress (project_id);

CREATE INDEX IF NOT EXISTS ix_session_namespace 
    ON session_progress (project_id, namespace);

COMMENT ON TABLE session_progress IS 'Tracks long-running task progress across context windows';

-- =============================================================================
-- Feature Tracker Table
-- =============================================================================

CREATE TABLE IF NOT EXISTS feature_tracker (
    id VARCHAR(32) PRIMARY KEY,
    project_id VARCHAR(64) NOT NULL,
    feature_id VARCHAR(128) NOT NULL,
    session_id VARCHAR(64),
    namespace VARCHAR(64) NOT NULL DEFAULT 'default',
    
    -- Feature definition
    description TEXT NOT NULL,
    category VARCHAR(64),
    test_steps JSONB DEFAULT '[]',
    
    -- Status tracking
    status VARCHAR(16) NOT NULL DEFAULT 'not_started'
        CHECK (status IN ('not_started', 'in_progress', 'blocked', 'testing', 'complete', 'failed')),
    passes BOOLEAN DEFAULT false,
    
    -- Implementation tracking
    implemented_by VARCHAR(64),
    verified_by VARCHAR(64),
    implementation_notes TEXT,
    failure_reason TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Unique constraint per project/namespace/feature
    CONSTRAINT uq_feature_project UNIQUE (project_id, namespace, feature_id)
);

CREATE INDEX IF NOT EXISTS ix_feature_project 
    ON feature_tracker (project_id);

CREATE INDEX IF NOT EXISTS ix_feature_session 
    ON feature_tracker (project_id, session_id);

CREATE INDEX IF NOT EXISTS ix_feature_status 
    ON feature_tracker (project_id, namespace, status);

COMMENT ON TABLE feature_tracker IS 'Tracks feature implementation status to prevent premature task completion';

-- =============================================================================
-- ROLLBACK (uncomment to rollback this migration)
-- =============================================================================
-- DROP TABLE IF EXISTS feature_tracker;
-- DROP TABLE IF EXISTS session_progress;
-- DROP TABLE IF EXISTS vote_history;
-- ALTER TABLE memories DROP COLUMN IF EXISTS source_trajectory_id;
-- ALTER TABLE memories DROP COLUMN IF EXISTS applicable_contexts;
-- ALTER TABLE memories DROP COLUMN IF EXISTS correct_approach;
-- ALTER TABLE memories DROP COLUMN IF EXISTS error_pattern;
-- ALTER TABLE memories DROP COLUMN IF EXISTS bullet_harmful;
-- ALTER TABLE memories DROP COLUMN IF EXISTS bullet_helpful;
-- ALTER TABLE memories DROP COLUMN IF EXISTS deprecation_reason;
-- ALTER TABLE memories DROP COLUMN IF EXISTS superseded_by;
-- ALTER TABLE memories DROP COLUMN IF EXISTS deprecated_at;
-- ALTER TABLE memories DROP COLUMN IF EXISTS is_deprecated;
-- ALTER TABLE memories DROP COLUMN IF EXISTS memory_type;

