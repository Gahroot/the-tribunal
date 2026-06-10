"""inbound spam screening + reason-based routing columns on messages

Revision ID: 20260611_inbound_screening
Revises: 20260610_caller_memory
Create Date: 2026-06-11 00:00:00.000000

Adds three nullable columns to ``messages`` capturing the inbound-call
screening outcome and the reason-based routing decision:

* ``screening_decision`` — allow / low_priority / challenge / reject
* ``screening_reason``    — why the decision was made (global_opt_out,
  blocklist, reputation_spam, high_call_volume, ...)
* ``routing_reason``      — classified caller intent used to pick the
  destination agent/queue (billing, sales, support, ...)

All columns are nullable; existing rows and non-voice messages keep NULLs.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260611_inbound_screening"
down_revision: str | Sequence[str] | None = "20260610_caller_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("screening_decision", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("screening_reason", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("routing_reason", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "routing_reason")
    op.drop_column("messages", "screening_reason")
    op.drop_column("messages", "screening_decision")
