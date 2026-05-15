"""Add username_hash to auth_rate_limits for per-username lockout.

Revision ID: c5d6e7f8a9b0
Revises: b4819c8748a9
Create Date: 2026-05-14 22:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5d6e7f8a9b0"
down_revision: str | None = "b4819c8748a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable username_hash column with an index for lockout lookups."""
    op.add_column(
        "auth_rate_limits",
        sa.Column("username_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_auth_rate_limits_username_hash",
        "auth_rate_limits",
        ["username_hash"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_auth_rate_limits_username_hash",
        table_name="auth_rate_limits",
    )
    op.drop_column("auth_rate_limits", "username_hash")
