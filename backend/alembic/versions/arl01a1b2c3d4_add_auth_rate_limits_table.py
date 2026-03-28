"""Add auth_rate_limits table.

Revision ID: arl01a1b2c3d4
Revises: 1963647ee64e
Create Date: 2026-03-27 13:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "arl01a1b2c3d4"
down_revision: str | None = "1963647ee64e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_rate_limits",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_ip", sa.String(100), nullable=False, index=True),
        sa.Column("endpoint", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("auth_rate_limits")
