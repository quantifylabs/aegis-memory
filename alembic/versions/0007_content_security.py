"""Add content security columns to memories and api_keys tables

Revision ID: 0007
Revises: 0006
Create Date: 2026-02-25

Notes:
  - integrity_hash stores HMAC-SHA256 for tamper detection.
    Nullable so existing rows don't need backfill. New memories always get one.
  - content_flags is a JSON array of string tags (e.g., ["pii_detected", "injection_flagged"]).
    Server_default='[]' for zero-downtime migration.
  - trust_level defaults to 'internal' matching the existing implicit behavior
    where all authenticated agents have equal access within a project.
  - bound_agent_id on api_keys enables agent identity binding — when set,
    the API key can only be used by that specific agent_id.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- memories table ---
    op.add_column(
        "memories",
        sa.Column("integrity_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "memories",
        sa.Column(
            "content_flags",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "memories",
        sa.Column(
            "trust_level",
            sa.String(16),
            nullable=False,
            server_default="internal",
        ),
    )

    # --- api_keys table ---
    op.add_column(
        "api_keys",
        sa.Column(
            "trust_level",
            sa.String(16),
            nullable=False,
            server_default="internal",
        ),
    )
    op.add_column(
        "api_keys",
        sa.Column("bound_agent_id", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "bound_agent_id")
    op.drop_column("api_keys", "trust_level")
    op.drop_column("memories", "trust_level")
    op.drop_column("memories", "content_flags")
    op.drop_column("memories", "integrity_hash")
