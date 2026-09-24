"""Add per-agent bandit reward weights.

Revision ID: 20260923_bandit_reward_config
Revises: 20260923_outbound_brief
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20260923_bandit_reward_config"
down_revision = "20260923_outbound_brief"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "bandit_reward_config", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "bandit_reward_config")
