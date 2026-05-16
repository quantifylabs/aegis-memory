"""Memory Depth: tsvector, memory_edges (v2.4.0)

Revision ID: 0009_memory_depth
Revises: 0008_context_hub
Create Date: 2026-05-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0009_memory_depth"
down_revision = "0008_context_hub"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- [P1] Sparse retrieval: tsvector column + GIN ----------
    op.execute("""
        ALTER TABLE memories
        ADD COLUMN content_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
    """)
    op.execute(
        "CREATE INDEX ix_memories_content_tsv ON memories USING GIN(content_tsv)"
    )

    # Optional but recommended: same for interaction_events for cross-event search
    op.execute("""
        ALTER TABLE interaction_events
        ADD COLUMN content_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
    """)
    op.execute(
        "CREATE INDEX ix_events_content_tsv ON interaction_events USING GIN(content_tsv)"
    )

    # ---------- [P2] Memory edges ----------
    op.create_table(
        "memory_edges",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("source_memory_id", sa.String(32), nullable=False),
        sa.Column("target_memory_id", sa.String(32), nullable=False),
        sa.Column("edge_type", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("detected_by", sa.String(64), nullable=False, server_default="manual"),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("metadata", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("resolution", sa.String(32), nullable=False, server_default="unresolved"),
        sa.Column("resolved_by", sa.String(64), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_edges_source", "memory_edges", ["project_id", "source_memory_id"])
    op.create_index("ix_edges_target", "memory_edges", ["project_id", "target_memory_id"])
    op.create_index("ix_edges_type_resolution", "memory_edges", ["project_id", "edge_type", "resolution"])
    op.create_index("ix_edges_pair_unique", "memory_edges",
                    ["source_memory_id", "target_memory_id", "edge_type"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_edges_pair_unique", table_name="memory_edges")
    op.drop_index("ix_edges_type_resolution", table_name="memory_edges")
    op.drop_index("ix_edges_target", table_name="memory_edges")
    op.drop_index("ix_edges_source", table_name="memory_edges")
    op.drop_table("memory_edges")
    op.execute("DROP INDEX IF EXISTS ix_events_content_tsv")
    op.execute("ALTER TABLE interaction_events DROP COLUMN IF EXISTS content_tsv")
    op.execute("DROP INDEX IF EXISTS ix_memories_content_tsv")
    op.execute("ALTER TABLE memories DROP COLUMN IF EXISTS content_tsv")
