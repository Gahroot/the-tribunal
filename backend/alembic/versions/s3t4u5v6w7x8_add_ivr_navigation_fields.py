"""Add IVR navigation fields to agents table.

Revision ID: s3t4u5v6w7x8
Revises: r2s3t4u5v6w7
Create Date: 2026-01-30

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "s3t4u5v6w7x8"
down_revision: str | None = "r2s3t4u5v6w7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add IVR navigation fields to agents table
    op.add_column(
        "agents",
        sa.Column(
            "enable_ivr_navigation",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "agents",
        sa.Column("ivr_navigation_goal", sa.Text(), nullable=True),
    )
    op.add_column(
        "agents",
        sa.Column(
            "ivr_loop_threshold",
            sa.Integer(),
            nullable=False,
            server_default="2",
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "ivr_loop_threshold")
    op.drop_column("agents", "ivr_navigation_goal")
    op.drop_column("agents", "enable_ivr_navigation")
