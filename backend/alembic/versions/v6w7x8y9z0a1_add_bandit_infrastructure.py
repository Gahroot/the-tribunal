"""Add multi-armed bandit infrastructure.

Adds:
- context JSONB column to call_outcomes for decision-time context
- bandit_alpha, bandit_beta, total_reward, reward_count to prompt_versions
- bandit_decisions table for tracking arm selections

Revision ID: v6w7x8y9z0a1
Revises: u5v6w7x8y9z0
Create Date: 2026-02-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v6w7x8y9z0a1"
down_revision: str | None = "u5v6w7x8y9z0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add context column to call_outcomes
    op.add_column(
        "call_outcomes",
        sa.Column("context", postgresql.JSONB(), nullable=True, server_default="{}"),
    )

    # Add bandit stats columns to prompt_versions
    op.add_column(
        "prompt_versions",
        sa.Column("bandit_alpha", sa.Float(), nullable=False, server_default="1.0"),
    )
    op.add_column(
        "prompt_versions",
        sa.Column("bandit_beta", sa.Float(), nullable=False, server_default="1.0"),
    )
    op.add_column(
        "prompt_versions",
        sa.Column("total_reward", sa.Float(), nullable=False, server_default="0.0"),
    )
    op.add_column(
        "prompt_versions",
        sa.Column("reward_count", sa.Integer(), nullable=False, server_default="0"),
    )

    # Create bandit_decisions table
    op.create_table(
        "bandit_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("arm_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decision_type", sa.String(50), nullable=False),
        sa.Column("exploration_rate", sa.Float(), nullable=True),
        sa.Column(
            "arm_statistics", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column(
            "context_snapshot", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column("observed_reward", sa.Float(), nullable=True),
        sa.Column("reward_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["arm_id"], ["prompt_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_bandit_decisions_agent_id", "bandit_decisions", ["agent_id"], unique=False
    )
    op.create_index(
        "ix_bandit_decisions_arm_id", "bandit_decisions", ["arm_id"], unique=False
    )
    op.create_index(
        "ix_bandit_decisions_message_id",
        "bandit_decisions",
        ["message_id"],
        unique=True,
    )
    op.create_index(
        "ix_bandit_decisions_created_at",
        "bandit_decisions",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    # Drop bandit_decisions table
    op.drop_index("ix_bandit_decisions_created_at", table_name="bandit_decisions")
    op.drop_index("ix_bandit_decisions_message_id", table_name="bandit_decisions")
    op.drop_index("ix_bandit_decisions_arm_id", table_name="bandit_decisions")
    op.drop_index("ix_bandit_decisions_agent_id", table_name="bandit_decisions")
    op.drop_table("bandit_decisions")

    # Drop bandit stats columns from prompt_versions
    op.drop_column("prompt_versions", "reward_count")
    op.drop_column("prompt_versions", "total_reward")
    op.drop_column("prompt_versions", "bandit_beta")
    op.drop_column("prompt_versions", "bandit_alpha")

    # Drop context column from call_outcomes
    op.drop_column("call_outcomes", "context")
