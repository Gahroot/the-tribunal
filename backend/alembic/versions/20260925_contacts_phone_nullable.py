"""Allow email-only contacts: make contacts.phone_number/phone_hash nullable.

Public offer opt-ins default to email-required, phone-optional. Those leads
were previously only counted, never saved as contacts, because the contact row
required a phone. This relaxes the constraint so the lead is kept.

Production safety: ``DROP NOT NULL`` is a catalog-only change in Postgres — no
table rewrite, no backfill, and every existing row (all of which have a phone)
is untouched. It takes a brief ACCESS EXCLUSIVE lock, bounded by lock_timeout.

Revision ID: 20260925_contacts_phone_nullable
Revises: 20260924_voice_experiments
"""

import sqlalchemy as sa

from alembic import op

revision = "20260925_contacts_phone_nullable"
down_revision = "20260924_voice_experiments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fail fast instead of queueing behind long transactions on a hot table.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.alter_column("contacts", "phone_number", existing_type=sa.Text(), nullable=True)
    op.alter_column("contacts", "phone_hash", existing_type=sa.Text(), nullable=True)
    op.execute("SET LOCAL lock_timeout = DEFAULT")


def downgrade() -> None:
    # Never delete or fabricate data to satisfy the old constraint: refuse when
    # phoneless contacts exist so an operator can decide what to do with them.
    bind = op.get_bind()
    phoneless = bind.execute(
        sa.text("SELECT count(*) FROM contacts WHERE phone_number IS NULL OR phone_hash IS NULL")
    ).scalar_one()
    if phoneless:
        raise RuntimeError(
            f"Refusing downgrade: {phoneless} contact(s) have no phone number. "
            "Resolve them manually before restoring the NOT NULL constraint."
        )
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.alter_column("contacts", "phone_hash", existing_type=sa.Text(), nullable=False)
    op.alter_column("contacts", "phone_number", existing_type=sa.Text(), nullable=False)
    op.execute("SET LOCAL lock_timeout = DEFAULT")
