-- Aegis Memory Initial Schema
-- Version: 1.0.0
-- Description: Creates the core memories table with pgvector support

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create memories table
CREATE TABLE IF NOT EXISTS memories (
    id VARCHAR(32) PRIMARY KEY,
    project_id VARCHAR(64) NOT NULL,
    content TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    embedding vector(1536),
    
    -- Ownership
    user_id VARCHAR(64),
    agent_id VARCHAR(64),
    namespace VARCHAR(64) NOT NULL DEFAULT 'default',
    
    -- Scope and sharing
    scope VARCHAR(16) NOT NULL DEFAULT 'agent-private',
    shared_with_agents JSONB DEFAULT '[]',
    derived_from_agents JSONB DEFAULT '[]',
    coordination_metadata JSONB DEFAULT '{}',
    
    -- Metadata
    metadata_json JSONB DEFAULT '{}',
    
    -- TTL
    expires_at TIMESTAMPTZ,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS ix_memories_project_namespace 
    ON memories (project_id, namespace);

CREATE INDEX IF NOT EXISTS ix_memories_project_agent 
    ON memories (project_id, agent_id);

CREATE INDEX IF NOT EXISTS ix_memories_project_user 
    ON memories (project_id, user_id);

CREATE INDEX IF NOT EXISTS ix_memories_content_hash 
    ON memories (content_hash);

CREATE INDEX IF NOT EXISTS ix_memories_expires_at 
    ON memories (expires_at) 
    WHERE expires_at IS NOT NULL;

-- Create HNSW index for vector similarity search
-- This provides O(log n) search instead of O(n)
CREATE INDEX IF NOT EXISTS ix_memories_embedding_hnsw 
    ON memories 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Create composite index for scope-aware queries
CREATE INDEX IF NOT EXISTS ix_memories_scope_access 
    ON memories (project_id, namespace, scope, agent_id);

-- Add comment
COMMENT ON TABLE memories IS 'Core memory storage with vector embeddings for semantic search';

-- =============================================================================
-- ROLLBACK (uncomment to rollback this migration)
-- =============================================================================
-- DROP INDEX IF EXISTS ix_memories_scope_access;
-- DROP INDEX IF EXISTS ix_memories_embedding_hnsw;
-- DROP INDEX IF EXISTS ix_memories_expires_at;
-- DROP INDEX IF EXISTS ix_memories_content_hash;
-- DROP INDEX IF EXISTS ix_memories_project_user;
-- DROP INDEX IF EXISTS ix_memories_project_agent;
-- DROP INDEX IF EXISTS ix_memories_project_namespace;
-- DROP TABLE IF EXISTS memories;
-- DROP EXTENSION IF EXISTS vector;

