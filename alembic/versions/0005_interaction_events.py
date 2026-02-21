"""Add interaction_events table for lightweight multi-agent collaboration history

Revision ID: 0005
Revises: 0004
Create Date: 2026-02-21

Notes:
  - HNSW index on nullable embedding column: pgvector >= 0.5.0 skips NULL rows
    automatically, so no partial-index WHERE clause is needed on the HNSW index.
  - Self-referential FK (parent_event_id → event_id) with ON DELETE SET NULL
    preserves child events when a parent is deleted.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "interaction_events",
        sa.Column("event_id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("tool_calls", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "parent_event_id",
            sa.String(32),
            sa.ForeignKey("interaction_events.event_id", ondelete="SET NULL", name="fk_interaction_parent"),
            nullable=True,
        ),
        sa.Column("namespace", sa.String(64), nullable=False, server_default="default"),
        sa.Column("extra_metadata", sa.JSON(), nullable=True),
        # Nullable: only populated when embed=True is requested at creation time.
        # pgvector >= 0.5.0 automatically skips NULL rows in HNSW indexes.
        sa.Column("embedding", sa.Text(), nullable=True),  # stored as vector by pgvector
    )

    op.create_index(
        "ix_interaction_project_session_ts",
        "interaction_events",
        ["project_id", "session_id", "timestamp"],
    )
    op.create_index(
        "ix_interaction_project_agent_ts",
        "interaction_events",
        ["project_id", "agent_id", "timestamp"],
    )
    op.create_index(
        "ix_interaction_parent",
        "interaction_events",
        ["parent_event_id"],
        postgresql_where=sa.text("parent_event_id IS NOT NULL"),
    )
    # HNSW index for cosine similarity search on embeddings.
    # pgvector >= 0.5.0 skips NULL embedding rows automatically.
    op.create_index(
        "ix_interaction_embedding_hnsw",
        "interaction_events",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_interaction_embedding_hnsw", table_name="interaction_events")
    op.drop_index("ix_interaction_parent", table_name="interaction_events")
    op.drop_index("ix_interaction_project_agent_ts", table_name="interaction_events")
    op.drop_index("ix_interaction_project_session_ts", table_name="interaction_events")
    op.drop_table("interaction_events")
