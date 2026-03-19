"""Add multi-touch reminder fields.

Revision ID: e3f4g5h6i7j8
Revises: d2e3f4g5h6i7
Create Date: 2026-03-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e3f4g5h6i7j8"
down_revision: str | None = "d2e3f4g5h6i7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "reminder_offsets",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default=sa.text("'{1440,120,30}'"),
        ),
    )
    op.add_column(
        "agents",
        sa.Column("reminder_template", sa.Text(), nullable=True),
    )
    op.add_column(
        "appointments",
        sa.Column(
            "reminders_sent",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("appointments", "reminders_sent")
    op.drop_column("agents", "reminder_template")
    op.drop_column("agents", "reminder_offsets")
