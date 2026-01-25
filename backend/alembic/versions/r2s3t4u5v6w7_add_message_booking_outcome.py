"""Add booking_outcome to messages.

Revision ID: r2s3t4u5v6w7
Revises: q1r2s3t4u5v6
Create Date: 2025-01-25 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "r2s3t4u5v6w7"
down_revision: str | None = "q1r2s3t4u5v6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add booking_outcome column to messages table."""
    op.add_column(
        "messages",
        sa.Column("booking_outcome", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    """Remove booking_outcome column from messages table."""
    op.drop_column("messages", "booking_outcome")
