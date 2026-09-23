"""Store a per-dial outbound research brief.

Revision ID: 20260923_outbound_brief
Revises: 20260923_booking_deposits
"""

import sqlalchemy as sa

from alembic import op

revision = "20260923_outbound_brief"
down_revision = "20260923_booking_deposits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("outbound_brief", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "outbound_brief")
