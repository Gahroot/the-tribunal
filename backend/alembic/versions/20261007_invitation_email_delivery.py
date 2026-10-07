"""Track invitation email delivery separately from invitation status.

Invitations were reported as "sent" even when the email provider rejected the
message or was not configured. These columns record the real outcome of each
send attempt so the API/UI can surface failures and offer a resend.

Production safety: nullable columns and a constant ``server_default`` are
catalog-only ``ADD COLUMN`` operations in Postgres 11+ — no table rewrite and
no backfill. Existing rows keep ``email_status = NULL`` (delivery unknown).

Revision ID: 20261007_invite_email_delivery
Revises: 20261007_appt_cancel_reason
"""

import sqlalchemy as sa

from alembic import op

revision = "20261007_invite_email_delivery"
down_revision = "20261007_appt_cancel_reason"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column(
        "workspace_invitations",
        sa.Column("email_status", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "workspace_invitations",
        sa.Column("email_attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "workspace_invitations",
        sa.Column("email_last_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workspace_invitations",
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("SET LOCAL lock_timeout = DEFAULT")


def downgrade() -> None:
    # Development rollback only: discards recorded invitation delivery outcomes.
    op.drop_column("workspace_invitations", "email_sent_at")
    op.drop_column("workspace_invitations", "email_last_attempt_at")
    op.drop_column("workspace_invitations", "email_attempt_count")
    op.drop_column("workspace_invitations", "email_status")
