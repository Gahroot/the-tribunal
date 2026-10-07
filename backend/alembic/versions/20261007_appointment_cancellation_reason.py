"""Store the operator/provider cancellation reason on appointments.

The cancel flow previously overwrote ``appointments.notes`` with the reason,
destroying existing notes. A dedicated nullable column keeps both.

Production safety: a nullable ``ADD COLUMN`` without a default is
catalog-only in Postgres — no table rewrite and no backfill.

Revision ID: 20261007_appt_cancel_reason
Revises: 20260925_contacts_phone_nullable
"""

import sqlalchemy as sa

from alembic import op

revision = "20261007_appt_cancel_reason"
down_revision = "20260925_contacts_phone_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column("appointments", sa.Column("cancellation_reason", sa.Text(), nullable=True))
    op.execute("SET LOCAL lock_timeout = DEFAULT")


def downgrade() -> None:
    # Development rollback only: discards stored cancellation reasons.
    op.drop_column("appointments", "cancellation_reason")
