"""Add opt-in campaign voice experiments and immutable contact assignments.

Revision ID: 20260924_voice_experiments
Revises: 20260923_model_configs
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260924_voice_experiments"
down_revision = "20260923_model_configs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable additions only: no rewrite/backfill of live CRM contacts.
    op.add_column("campaigns", sa.Column("voice_experiment", postgresql.JSONB(), nullable=True))
    op.add_column(
        "campaign_contacts", sa.Column("voice_assignment", postgresql.JSONB(), nullable=True)
    )


def downgrade() -> None:
    # Development rollback only: discards experiment configuration and attribution.
    op.drop_column("campaign_contacts", "voice_assignment")
    op.drop_column("campaigns", "voice_experiment")
