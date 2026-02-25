"""Add last_accessed_at and access_count columns for temporal decay

Revision ID: 0006
Revises: 0005
Create Date: 2026-02-22

Notes:
  - last_accessed_at is nullable (NULL means never explicitly accessed;
    decay falls back to created_at in that case).
  - access_count has server_default="0" so existing rows get 0 without
    a full-table rewrite; zero-downtime safe.
  - Partial index ix_memories_last_accessed on (project_id, last_accessed_at)
    WHERE last_accessed_at IS NOT NULL supports efficient decay sweep queries.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "memories",
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "memories",
        sa.Column(
            "access_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index(
        "ix_memories_last_accessed",
        "memories",
        ["project_id", "last_accessed_at"],
        postgresql_where=sa.text("last_accessed_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_memories_last_accessed", table_name="memories")
    op.drop_column("memories", "access_count")
    op.drop_column("memories", "last_accessed_at")
