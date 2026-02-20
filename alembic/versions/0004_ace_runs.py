"""Add ace_runs table for ACE loop run tracking

Revision ID: 0004
Revises: 0003
Create Date: 2026-02-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ace_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=True),
        sa.Column("task_type", sa.String(64), nullable=True),
        sa.Column("namespace", sa.String(64), nullable=False, server_default="default"),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("evaluation", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("logs", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("memory_ids_used", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("reflection_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_ace_runs_project_run", "ace_runs", ["project_id", "run_id"], unique=True)
    op.create_index("ix_ace_runs_project_agent", "ace_runs", ["project_id", "agent_id"])
    op.create_index("ix_ace_runs_project_task_type", "ace_runs", ["project_id", "task_type"])


def downgrade() -> None:
    op.drop_index("ix_ace_runs_project_task_type", table_name="ace_runs")
    op.drop_index("ix_ace_runs_project_agent", table_name="ace_runs")
    op.drop_index("ix_ace_runs_project_run", table_name="ace_runs")
    op.drop_table("ace_runs")
