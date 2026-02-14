"""Add typed memory columns and indexes for cognitive memory types

Revision ID: 0003
Revises: 0002
Create Date: 2026-02-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Widen memory_type column from String(16) to String(32)
    op.alter_column(
        "memories",
        "memory_type",
        type_=sa.String(32),
        existing_type=sa.String(16),
        existing_nullable=False,
    )

    # Add typed memory columns
    op.add_column("memories", sa.Column("session_id", sa.String(64), nullable=True))
    op.add_column("memories", sa.Column("entity_id", sa.String(128), nullable=True))
    op.add_column("memories", sa.Column("sequence_number", sa.Integer(), nullable=True))

    # Partial indexes for session and entity queries
    op.create_index(
        "ix_memories_session",
        "memories",
        ["project_id", "session_id"],
        postgresql_where=sa.text("session_id IS NOT NULL"),
    )
    op.create_index(
        "ix_memories_entity",
        "memories",
        ["project_id", "entity_id"],
        postgresql_where=sa.text("entity_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_memories_entity", table_name="memories")
    op.drop_index("ix_memories_session", table_name="memories")

    op.drop_column("memories", "sequence_number")
    op.drop_column("memories", "entity_id")
    op.drop_column("memories", "session_id")

    op.alter_column(
        "memories",
        "memory_type",
        type_=sa.String(16),
        existing_type=sa.String(32),
        existing_nullable=False,
    )
