"""Enable multi-variant A/B testing for prompt versions.

Adds:
- traffic_percentage: Fixed traffic allocation (0-100) for non-bandit testing
- experiment_id: Groups related variants in the same experiment
- arm_status: Tracks arm lifecycle (active, paused, eliminated)

Revision ID: w7x8y9z0a1b2
Revises: v6w7x8y9z0a1
Create Date: 2026-02-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "w7x8y9z0a1b2"
down_revision: str | None = "v6w7x8y9z0a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add traffic_percentage for fixed allocation A/B testing
    op.add_column(
        "prompt_versions",
        sa.Column("traffic_percentage", sa.Integer(), nullable=True),
    )

    # Add experiment_id to group variants together
    op.add_column(
        "prompt_versions",
        sa.Column("experiment_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_prompt_versions_experiment_id",
        "prompt_versions",
        ["experiment_id"],
        unique=False,
    )

    # Add arm_status for tracking arm lifecycle
    op.add_column(
        "prompt_versions",
        sa.Column(
            "arm_status",
            sa.String(20),
            nullable=False,
            server_default="active",
        ),
    )
    op.create_index(
        "ix_prompt_versions_arm_status",
        "prompt_versions",
        ["arm_status"],
        unique=False,
    )

    # Add composite index for efficient active arm queries
    op.create_index(
        "ix_prompt_versions_agent_active_arms",
        "prompt_versions",
        ["agent_id", "is_active", "arm_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_prompt_versions_agent_active_arms", table_name="prompt_versions")
    op.drop_index("ix_prompt_versions_arm_status", table_name="prompt_versions")
    op.drop_index("ix_prompt_versions_experiment_id", table_name="prompt_versions")
    op.drop_column("prompt_versions", "arm_status")
    op.drop_column("prompt_versions", "experiment_id")
    op.drop_column("prompt_versions", "traffic_percentage")
