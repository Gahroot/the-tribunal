"""add lead magnet delivery status fields

Revision ID: rf201delivery
Revises: a0e8a88f7801
Create Date: 2026-06-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "rf201delivery"
down_revision: Union[str, None] = "a0e8a88f7801"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "lead_magnet_leads",
        sa.Column("delivery_attempted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("lead_magnet_leads", sa.Column("delivery_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("lead_magnet_leads", "delivery_error")
    op.drop_column("lead_magnet_leads", "delivery_attempted_at")
