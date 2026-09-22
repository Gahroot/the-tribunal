"""add structured offer ladder strategy metadata

Revision ID: 20260614_offer_ladder_strategy
Revises: rf505_nudge_cta
Create Date: 2026-06-14 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260614_offer_ladder_strategy"
down_revision: Union[str, None] = "rf505_nudge_cta"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "offers",
        sa.Column("package_options", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "offers",
        sa.Column("negotiation_sequence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "offers",
        sa.Column("strategy_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("offers", "strategy_metadata")
    op.drop_column("offers", "negotiation_sequence")
    op.drop_column("offers", "package_options")
