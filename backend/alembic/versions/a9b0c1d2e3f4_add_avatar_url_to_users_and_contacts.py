"""Add avatar_url to users and contacts.

Revision ID: a9b0c1d2e3f4
Revises: z8a9b0c1d2e3
Create Date: 2026-05-15 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9b0c1d2e3f4"
down_revision: str | None = "z8a9b0c1d2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("avatar_url", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column("avatar_url", sa.String(length=1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contacts", "avatar_url")
    op.drop_column("users", "avatar_url")
