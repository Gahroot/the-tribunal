"""Add opportunity status field.

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2025-01-05 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "h2i3j4k5l6m7"
down_revision: str | None = "g1h2i3j4k5l6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create the enum type
    opportunity_status = sa.Enum(
        "open", "won", "lost", "abandoned", name="opportunity_status"
    )
    opportunity_status.create(op.get_bind(), checkfirst=True)

    # Add status column with default 'open'
    op.add_column(
        "opportunities",
        sa.Column(
            "status",
            opportunity_status,
            nullable=False,
            server_default="open",
        ),
    )

    # Add lost_reason column
    op.add_column(
        "opportunities",
        sa.Column("lost_reason", sa.String(255), nullable=True),
    )

    # Add index on status for filtering
    op.create_index(
        "ix_opportunities_status", "opportunities", ["status"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_opportunities_status", table_name="opportunities")
    op.drop_column("opportunities", "lost_reason")
    op.drop_column("opportunities", "status")

    # Drop the enum type
    sa.Enum(name="opportunity_status").drop(op.get_bind(), checkfirst=True)
