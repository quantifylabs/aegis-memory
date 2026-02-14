"""Add memory_shared_agents join table for normalized ACLs

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "memory_shared_agents",
        sa.Column("memory_id", sa.String(32), sa.ForeignKey("memories.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("shared_agent_id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("namespace", sa.String(64), nullable=False, server_default="default"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_msa_memory_agent", "memory_shared_agents", ["memory_id", "shared_agent_id"], unique=True)
    op.create_index("ix_msa_query", "memory_shared_agents", ["project_id", "namespace", "shared_agent_id"])


def downgrade() -> None:
    op.drop_index("ix_msa_query", table_name="memory_shared_agents")
    op.drop_index("ix_msa_memory_agent", table_name="memory_shared_agents")
    op.drop_table("memory_shared_agents")
