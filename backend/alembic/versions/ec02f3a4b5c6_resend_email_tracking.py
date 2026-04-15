"""Resend email tracking.

Adds email-specific columns to messages, email_* counters to campaigns,
and creates the email_events table for Resend webhook tracking.

Revision ID: ec02f3a4b5c6
Revises: db01e2f3a4b5
Create Date: 2026-04-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "ec02f3a4b5c6"
down_revision: str | None = "db01e2f3a4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Message email columns
    op.add_column("messages", sa.Column("subject", sa.String(255), nullable=True))
    op.add_column("messages", sa.Column("recipient_email", sa.String(320), nullable=True))
    op.add_column("messages", sa.Column("sender_email", sa.String(320), nullable=True))

    # Campaign email stat columns
    for col in (
        "emails_sent",
        "emails_delivered",
        "emails_bounced",
        "emails_opened",
        "emails_clicked",
        "emails_unsubscribed",
    ):
        op.add_column(
            "campaigns",
            sa.Column(col, sa.Integer(), nullable=False, server_default="0"),
        )

    # email_events table
    op.create_table(
        "email_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("provider_event_id", sa.String(255), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_email_events_workspace_occurred",
        "email_events",
        ["workspace_id", "occurred_at"],
    )
    op.create_index("ix_email_events_message_id", "email_events", ["message_id"])
    op.create_index(
        "ix_email_events_provider_event_id",
        "email_events",
        ["provider_event_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_email_events_provider_event_id", table_name="email_events")
    op.drop_index("ix_email_events_message_id", table_name="email_events")
    op.drop_index("ix_email_events_workspace_occurred", table_name="email_events")
    op.drop_table("email_events")

    for col in (
        "emails_unsubscribed",
        "emails_clicked",
        "emails_opened",
        "emails_bounced",
        "emails_delivered",
        "emails_sent",
    ):
        op.drop_column("campaigns", col)

    op.drop_column("messages", "sender_email")
    op.drop_column("messages", "recipient_email")
    op.drop_column("messages", "subject")
