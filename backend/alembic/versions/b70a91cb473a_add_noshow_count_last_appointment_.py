"""add_noshow_count_last_appointment_status_to_contacts

Revision ID: b70a91cb473a
Revises: f0a1b2c3d4e5
Create Date: 2026-03-19 18:08:45.062742

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b70a91cb473a"
down_revision: str | None = "f0a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "contacts",
        sa.Column("noshow_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "contacts",
        sa.Column("last_appointment_status", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contacts", "last_appointment_status")
    op.drop_column("contacts", "noshow_count")
