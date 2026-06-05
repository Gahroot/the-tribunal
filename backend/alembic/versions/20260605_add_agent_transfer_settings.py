"""add live transfer/handoff settings to agents

Revision ID: 20260605_agent_transfer
Revises: 20260601_drop_contact_tags
Create Date: 2026-06-05

Adds per-agent live warm/cold transfer configuration so an AI voice agent can
hand an active call to a human closer:

- transfer_destination_number: where to route the human leg (E.164)
- transfer_mode: "warm" (speak briefing then bridge) or "cold" (bridge now)
- transfer_briefing_template: optional spoken briefing template for warm mode
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260605_agent_transfer"
down_revision: str | Sequence[str] | None = "20260601_drop_contact_tags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add transfer configuration columns to the agents table."""
    op.add_column(
        "agents",
        sa.Column("transfer_destination_number", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "agents",
        sa.Column(
            "transfer_mode",
            sa.String(length=10),
            server_default="warm",
            nullable=False,
        ),
    )
    op.add_column(
        "agents",
        sa.Column("transfer_briefing_template", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop the transfer configuration columns."""
    op.drop_column("agents", "transfer_briefing_template")
    op.drop_column("agents", "transfer_mode")
    op.drop_column("agents", "transfer_destination_number")
