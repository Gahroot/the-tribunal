"""Add push preference columns to users.

Revision ID: b0c1d2e3f4g5
Revises: a9b0c1d2e3f4
Create Date: 2026-02-22
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "b0c1d2e3f4g5"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("notification_push_calls", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "users",
        sa.Column("notification_push_messages", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "users",
        sa.Column("notification_push_voicemail", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("users", "notification_push_voicemail")
    op.drop_column("users", "notification_push_messages")
    op.drop_column("users", "notification_push_calls")
