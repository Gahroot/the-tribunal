"""Add agent embed fields for embeddable widgets.

Revision ID: q1r2s3t4u5v6
Revises: p0q1r2s3t4u5
Create Date: 2026-01-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "q1r2s3t4u5v6"
down_revision: str | None = "p0q1r2s3t4u5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add embed fields to agents table
    op.add_column(
        "agents",
        sa.Column("public_id", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "agents",
        sa.Column("embed_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "agents",
        sa.Column("allowed_domains", ARRAY(sa.Text()), nullable=False, server_default="{}"),
    )
    op.add_column(
        "agents",
        sa.Column("embed_settings", JSONB(), nullable=False, server_default="{}"),
    )
    # Create unique index on public_id
    op.create_index("ix_agents_public_id", "agents", ["public_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_agents_public_id", "agents")
    op.drop_column("agents", "embed_settings")
    op.drop_column("agents", "allowed_domains")
    op.drop_column("agents", "embed_enabled")
    op.drop_column("agents", "public_id")
