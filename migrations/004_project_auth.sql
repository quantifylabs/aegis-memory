-- Migration 004: Project-scoped authentication tables
-- Adds multi-tenant project isolation with API key management.
-- Safe to run on existing deployments (uses IF NOT EXISTS).

-- Projects table
CREATE TABLE IF NOT EXISTS projects (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- API keys table (key_hash stores SHA-256 of the raw key)
CREATE TABLE IF NOT EXISTS api_keys (
    id VARCHAR(32) PRIMARY KEY,
    project_id VARCHAR(64) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    key_hash VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(128) NOT NULL DEFAULT 'default',
    is_active BOOLEAN NOT NULL DEFAULT true,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_api_keys_project ON api_keys (project_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_api_keys_key_hash ON api_keys (key_hash);

-- Seed the default project so existing deployments keep working
INSERT INTO projects (id, name, description)
VALUES ('default-project', 'Default Project', 'Auto-created default project for legacy compatibility')
ON CONFLICT (id) DO NOTHING;
