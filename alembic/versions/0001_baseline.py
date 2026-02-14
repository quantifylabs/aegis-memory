"""Baseline migration from v1.3.0 schema

Captures all existing tables: memories, vote_history, session_progress,
feature_tracker, embedding_cache, memory_events, projects, api_keys.

Revision ID: 0001
Revises: None
Create Date: 2026-02-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # -- projects table --
    op.create_table(
        "projects",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # -- api_keys table --
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False, server_default="default"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_api_keys_project", "api_keys", ["project_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)

    # -- memories table --
    op.create_table(
        "memories",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("agent_id", sa.String(64), nullable=True),
        sa.Column("namespace", sa.String(64), nullable=False, server_default="default"),
        sa.Column("memory_type", sa.String(16), nullable=False, server_default="standard"),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("embedding", postgresql.ARRAY(sa.Float), nullable=False),  # pgvector Vector(1536) at DB level
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("scope", sa.String(16), nullable=False, server_default="agent-private"),
        sa.Column("shared_with_agents", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("derived_from_agents", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("coordination_metadata", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bullet_helpful", sa.Integer, nullable=False, server_default="0"),
        sa.Column("bullet_harmful", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_deprecated", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deprecated_by", sa.String(64), nullable=True),
        sa.Column("superseded_by", sa.String(32), nullable=True),
        sa.Column("source_trajectory_id", sa.String(64), nullable=True),
        sa.Column("error_pattern", sa.String(128), nullable=True),
    )
    op.create_index("ix_content_hash", "memories", ["content_hash"])
    op.create_index("ix_memories_project_ns_user", "memories", ["project_id", "namespace", "user_id"])
    op.create_index("ix_memories_project_ns_scope", "memories", ["project_id", "namespace", "scope"])
    op.create_index("ix_memories_project_agent", "memories", ["project_id", "agent_id"])
    op.create_index(
        "ix_memories_expires", "memories", ["expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )
    op.create_index("ix_memories_project_type", "memories", ["project_id", "namespace", "memory_type"])
    op.create_index(
        "ix_memories_active", "memories", ["project_id", "namespace", "is_deprecated"],
        postgresql_where=sa.text("is_deprecated = false"),
    )

    # HNSW index (pgvector) - must be executed as raw SQL
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_memories_embedding_hnsw
        ON memories USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    # -- vote_history table --
    op.create_table(
        "vote_history",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("memory_id", sa.String(32), sa.ForeignKey("memories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("voter_agent_id", sa.String(64), nullable=False),
        sa.Column("vote", sa.String(8), nullable=False),
        sa.Column("context", sa.Text, nullable=True),
        sa.Column("task_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_votes_memory", "vote_history", ["memory_id"])
    op.create_index("ix_votes_agent", "vote_history", ["project_id", "voter_agent_id"])

    # -- session_progress table --
    op.create_table(
        "session_progress",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=False, unique=True),
        sa.Column("agent_id", sa.String(64), nullable=True),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("namespace", sa.String(64), nullable=False, server_default="default"),
        sa.Column("completed_items", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("in_progress_item", sa.String(256), nullable=True),
        sa.Column("next_items", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("blocked_items", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("last_action", sa.Text, nullable=True),
        sa.Column("total_items", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_session_project", "session_progress", ["project_id", "namespace"])
    op.create_index("ix_session_agent", "session_progress", ["project_id", "agent_id"])

    # -- feature_tracker table --
    op.create_table(
        "feature_tracker",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("namespace", sa.String(64), nullable=False, server_default="default"),
        sa.Column("feature_id", sa.String(128), nullable=False),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("test_steps", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False, server_default="not_started"),
        sa.Column("passes", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("implemented_by", sa.String(64), nullable=True),
        sa.Column("verified_by", sa.String(64), nullable=True),
        sa.Column("implementation_notes", sa.Text, nullable=True),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_feature_project", "feature_tracker", ["project_id", "namespace"])
    op.create_index("ix_feature_session", "feature_tracker", ["session_id"])
    op.create_index("ix_feature_status", "feature_tracker", ["project_id", "status"])
    op.create_index(
        "ix_feature_unique", "feature_tracker",
        ["project_id", "namespace", "feature_id"],
        unique=True,
    )

    # -- embedding_cache table --
    op.create_table(
        "embedding_cache",
        sa.Column("content_hash", sa.String(64), primary_key=True),
        sa.Column("embedding", postgresql.ARRAY(sa.Float), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("hit_count", sa.Integer, nullable=False, server_default="0"),
    )

    # -- memory_events table --
    op.create_table(
        "memory_events",
        sa.Column("event_id", sa.String(32), primary_key=True),
        sa.Column("memory_id", sa.String(32), sa.ForeignKey("memories.id", ondelete="CASCADE"), nullable=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("namespace", sa.String(64), nullable=False, server_default="default"),
        sa.Column("agent_id", sa.String(64), nullable=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("task_id", sa.String(128), nullable=True),
        sa.Column("retrieval_event_id", sa.String(32), nullable=True),
        sa.Column("selected_memory_ids", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("event_payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_memory_events_project_created", "memory_events", ["project_id", "created_at"])
    op.create_index("ix_memory_events_memory_created", "memory_events", ["memory_id", "created_at"])
    op.create_index("ix_memory_events_project_task", "memory_events", ["project_id", "task_id"])
    op.create_index("ix_memory_events_project_retrieval", "memory_events", ["project_id", "retrieval_event_id"])

    # Seed default project
    op.execute("""
        INSERT INTO projects (id, name, description)
        VALUES ('default-project', 'Default Project', 'Auto-created default project for legacy compatibility')
        ON CONFLICT (id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("memory_events")
    op.drop_table("embedding_cache")
    op.drop_table("feature_tracker")
    op.drop_table("session_progress")
    op.drop_table("vote_history")
    op.drop_table("memories")
    op.drop_table("api_keys")
    op.drop_table("projects")
    op.execute("DROP EXTENSION IF EXISTS vector")
