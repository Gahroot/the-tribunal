"""add nudge CTA fields

Revision ID: rf505_nudge_cta
Revises: rf201delivery
Create Date: 2026-06-14 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "rf505_nudge_cta"
down_revision: Union[str, None] = "rf201delivery"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("human_nudges", sa.Column("cta_label", sa.String(length=80), nullable=True))
    op.add_column("human_nudges", sa.Column("href", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("human_nudges", "href")
    op.drop_column("human_nudges", "cta_label")
