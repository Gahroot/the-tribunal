"""Add IVR timing configuration fields to agents table.

Revision ID: t4u5v6w7x8y9
Revises: s3t4u5v6w7x8
Create Date: 2026-02-01

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "t4u5v6w7x8y9"
down_revision: str | None = "s3t4u5v6w7x8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add IVR timing configuration fields to agents table
    # These allow per-agent customization of IVR navigation timing

    # Silence duration before AI responds (wait for complete menu)
    op.add_column(
        "agents",
        sa.Column(
            "ivr_silence_duration_ms",
            sa.Integer(),
            nullable=False,
            server_default="3000",
        ),
    )

    # Cooldown after sending DTMF (prevent rapid presses)
    op.add_column(
        "agents",
        sa.Column(
            "ivr_post_dtmf_cooldown_ms",
            sa.Integer(),
            nullable=False,
            server_default="3000",
        ),
    )

    # Buffer silence to accumulate transcript before responding
    op.add_column(
        "agents",
        sa.Column(
            "ivr_menu_buffer_silence_ms",
            sa.Integer(),
            nullable=False,
            server_default="2000",
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "ivr_menu_buffer_silence_ms")
    op.drop_column("agents", "ivr_post_dtmf_cooldown_ms")
    op.drop_column("agents", "ivr_silence_duration_ms")
