"""add_noshow_post_meeting_value_reinforce_never_booked_to_agents

Revision ID: 4b887f603893
Revises: b70a91cb473a
Create Date: 2026-03-19 18:09:53.057454

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4b887f603893"
down_revision: str | None = "b70a91cb473a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("noshow_template", sa.Text(), nullable=True))
    op.add_column(
        "agents",
        sa.Column(
            "post_meeting_sms_enabled",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.add_column("agents", sa.Column("post_meeting_template", sa.Text(), nullable=True))
    op.add_column(
        "agents",
        sa.Column(
            "value_reinforcement_enabled",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.add_column(
        "agents",
        sa.Column(
            "value_reinforcement_offset_minutes",
            sa.Integer(),
            server_default="120",
            nullable=False,
        ),
    )
    op.add_column(
        "agents", sa.Column("value_reinforcement_template", sa.Text(), nullable=True)
    )
    op.add_column(
        "agents",
        sa.Column(
            "never_booked_reengagement_enabled",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.add_column(
        "agents",
        sa.Column(
            "never_booked_delay_days",
            sa.Integer(),
            server_default="7",
            nullable=False,
        ),
    )
    op.add_column("agents", sa.Column("never_booked_template", sa.Text(), nullable=True))
    op.add_column(
        "agents",
        sa.Column(
            "never_booked_max_attempts",
            sa.Integer(),
            server_default="2",
            nullable=False,
        ),
    )
    op.add_column(
        "agents",
        sa.Column(
            "noshow_reengagement_enabled",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
    )
    op.add_column("agents", sa.Column("noshow_day3_template", sa.Text(), nullable=True))
    op.add_column("agents", sa.Column("noshow_day7_template", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "noshow_day7_template")
    op.drop_column("agents", "noshow_day3_template")
    op.drop_column("agents", "noshow_reengagement_enabled")
    op.drop_column("agents", "never_booked_max_attempts")
    op.drop_column("agents", "never_booked_template")
    op.drop_column("agents", "never_booked_delay_days")
    op.drop_column("agents", "never_booked_reengagement_enabled")
    op.drop_column("agents", "value_reinforcement_template")
    op.drop_column("agents", "value_reinforcement_offset_minutes")
    op.drop_column("agents", "value_reinforcement_enabled")
    op.drop_column("agents", "post_meeting_template")
    op.drop_column("agents", "post_meeting_sms_enabled")
    op.drop_column("agents", "noshow_template")
