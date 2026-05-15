"""Context Hub: prompts, skills, subagents (v2.3.0)

Revision ID: 0008_context_hub
Revises: 0007
Create Date: 2026-05-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector


revision = "0008_context_hub"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- prompts ----------
    op.create_table(
        "prompts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("namespace", sa.String(64), nullable=False, server_default="default"),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("variables", postgresql.JSON, nullable=False, server_default="[]"),
        sa.Column("tags", postgresql.JSON, nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_by_agent_id", sa.String(64), nullable=True),
        sa.Column("integrity_hash", sa.String(64), nullable=True),
        sa.Column("content_flags", postgresql.JSON, nullable=False, server_default="[]"),
        sa.Column("trust_level", sa.String(16), nullable=False, server_default="internal"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_prompts_lookup", "prompts", ["project_id", "namespace", "name"])
    op.create_index("ix_prompts_active", "prompts", ["project_id", "namespace", "name"],
                    postgresql_where=sa.text("is_active = true"))
    op.create_index("ix_prompts_version_unique", "prompts",
                    ["project_id", "namespace", "name", "version"], unique=True)

    # ---------- skills ----------
    op.create_table(
        "skills",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("namespace", sa.String(64), nullable=False, server_default="default"),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("description_embedding", Vector(1536), nullable=True),
        sa.Column("version", sa.String(32), nullable=False, server_default="1.0.0"),
        sa.Column("skill_md", sa.Text, nullable=False),
        sa.Column("bundled_files", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("metadata", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_by_agent_id", sa.String(64), nullable=True),
        sa.Column("integrity_hash", sa.String(64), nullable=True),
        sa.Column("content_flags", postgresql.JSON, nullable=False, server_default="[]"),
        sa.Column("trust_level", sa.String(16), nullable=False, server_default="privileged"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_skills_lookup", "skills", ["project_id", "namespace", "name"], unique=True)
    op.create_index("ix_skills_active", "skills", ["project_id", "namespace"],
                    postgresql_where=sa.text("is_active = true"))
    op.execute(
        "CREATE INDEX ix_skills_desc_hnsw ON skills USING hnsw "
        "(description_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )

    # ---------- subagents ----------
    op.create_table(
        "subagents",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("namespace", sa.String(64), nullable=False, server_default="default"),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("system_prompt", sa.Text, nullable=True),
        sa.Column("system_prompt_ref", sa.String(128), nullable=True),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("tools", postgresql.JSON, nullable=False, server_default="[]"),
        sa.Column("allowed_scopes", postgresql.JSON, nullable=False, server_default="[]"),
        sa.Column("allowed_skills", postgresql.JSON, nullable=False, server_default="[]"),
        sa.Column("parent_agent_id", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("integrity_hash", sa.String(64), nullable=True),
        sa.Column("trust_level", sa.String(16), nullable=False, server_default="internal"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_subagents_lookup", "subagents", ["project_id", "namespace", "name"], unique=True)
    op.create_index("ix_subagents_parent", "subagents", ["project_id", "parent_agent_id"])


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_skills_desc_hnsw")
    op.drop_index("ix_subagents_parent", table_name="subagents")
    op.drop_index("ix_subagents_lookup", table_name="subagents")
    op.drop_table("subagents")
    op.drop_index("ix_skills_active", table_name="skills")
    op.drop_index("ix_skills_lookup", table_name="skills")
    op.drop_table("skills")
    op.drop_index("ix_prompts_version_unique", table_name="prompts")
    op.drop_index("ix_prompts_active", table_name="prompts")
    op.drop_index("ix_prompts_lookup", table_name="prompts")
    op.drop_table("prompts")
