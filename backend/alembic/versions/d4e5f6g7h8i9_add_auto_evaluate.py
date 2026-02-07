"""Add auto_evaluate to agents.

Revision ID: d4e5f6g7h8i9
Revises: z8a9b0c1d2e3
Create Date: 2026-02-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6g7h8i9"
down_revision: str | None = "z8a9b0c1d2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("auto_evaluate", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("agents", "auto_evaluate")
