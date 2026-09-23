"""Add optional agent booking deposit settings and appointment assignment snapshot.

Revision ID: 20260923_booking_deposits
Revises: 20260923_appt_confirm
"""

import sqlalchemy as sa

from alembic import op

revision = "20260923_booking_deposits"
down_revision = "20260923_appt_confirm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("booking_deposit_mode", sa.String(20), nullable=False, server_default="off"),
    )
    op.create_check_constraint(
        "ck_agents_booking_deposit_mode",
        "agents",
        "booking_deposit_mode IN ('off', 'card', '20', '50', 'experiment')",
    )
    op.add_column(
        "appointments",
        sa.Column("deposit_experiment", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("appointments", sa.Column("deposit_amount_cents", sa.Integer(), nullable=True))
    op.add_column("appointments", sa.Column("deposit_status", sa.String(20), nullable=True))
    op.add_column(
        "appointments", sa.Column("deposit_checkout_session_id", sa.String(255), nullable=True)
    )
    op.add_column(
        "appointments", sa.Column("deposit_payment_intent_id", sa.String(255), nullable=True)
    )
    op.add_column(
        "appointments", sa.Column("deposit_setup_intent_id", sa.String(255), nullable=True)
    )
    op.add_column(
        "appointments", sa.Column("deposit_stripe_customer_id", sa.String(255), nullable=True)
    )
    op.add_column("appointments", sa.Column("deposit_refund_id", sa.String(255), nullable=True))
    op.add_column("appointments", sa.Column("deposit_checkout_url", sa.Text(), nullable=True))
    op.create_unique_constraint(
        "uq_appointments_deposit_checkout_session_id",
        "appointments",
        ["deposit_checkout_session_id"],
    )
    op.create_check_constraint(
        "ck_appointments_deposit_amount",
        "appointments",
        "deposit_amount_cents IN (0, 2000, 5000) OR deposit_amount_cents IS NULL",
    )
    op.create_check_constraint(
        "ck_appointments_deposit_status",
        "appointments",
        "deposit_status IN ('pending', 'paid', 'card_saved', 'refunded', "
        "'refund_pending', 'none') OR deposit_status IS NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_appointments_deposit_status", "appointments", type_="check")
    op.drop_constraint("ck_appointments_deposit_amount", "appointments", type_="check")
    op.drop_constraint(
        "uq_appointments_deposit_checkout_session_id", "appointments", type_="unique"
    )
    for name in (
        "deposit_experiment",
        "deposit_checkout_url",
        "deposit_payment_intent_id",
        "deposit_setup_intent_id",
        "deposit_stripe_customer_id",
        "deposit_refund_id",
        "deposit_checkout_session_id",
        "deposit_status",
        "deposit_amount_cents",
    ):
        op.drop_column("appointments", name)
    op.drop_constraint("ck_agents_booking_deposit_mode", "agents", type_="check")
    op.drop_column("agents", "booking_deposit_mode")
