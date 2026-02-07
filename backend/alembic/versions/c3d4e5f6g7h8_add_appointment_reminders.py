"""Add appointment reminders.

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-02-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6g7h8"
down_revision: str | None = "b2c3d4e5f6g7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add reminder fields to agents and appointments."""
    op.add_column(
        "agents",
        sa.Column(
            "reminder_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "agents",
        sa.Column(
            "reminder_minutes_before",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("30"),
        ),
    )
    op.add_column(
        "appointments",
        sa.Column(
            "reminder_sent_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove reminder fields."""
    op.drop_column("appointments", "reminder_sent_at")
    op.drop_column("agents", "reminder_minutes_before")
    op.drop_column("agents", "reminder_enabled")
