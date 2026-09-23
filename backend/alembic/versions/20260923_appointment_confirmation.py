"""Track appointment SMS confirmation and reschedule requests.

Revision ID: 20260923_appt_confirm
Revises: 20260709_agent_realtime_model
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260923_appt_confirm"
down_revision: str | None = "20260709_agent_realtime_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "appointments", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "appointments",
        sa.Column("reschedule_requested_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("appointments", "reschedule_requested_at")
    op.drop_column("appointments", "confirmed_at")
