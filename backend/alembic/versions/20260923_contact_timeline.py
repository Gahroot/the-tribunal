"""Add a canonical contact timeline without removing historical source records.

Revision ID: 20260923_contact_timeline
Revises: 20260923_bandit_reward_config
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "20260923_contact_timeline"
down_revision = "20260923_bandit_reward_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contact_timeline_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "contact_id",
            sa.BigInteger(),
            sa.ForeignKey("contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("facts", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "workspace_id", "source", "source_id", name="uq_contact_timeline_source"
        ),
    )
    op.create_index(
        "ix_contact_timeline_contact_time",
        "contact_timeline_events",
        ["workspace_id", "contact_id", "occurred_at"],
    )
    # Historical call memories are imported in bounded batches on contact read;
    # no unbounded production backfill or rewrite of existing customer data.


def downgrade() -> None:
    op.drop_index("ix_contact_timeline_contact_time", table_name="contact_timeline_events")
    op.drop_table("contact_timeline_events")
