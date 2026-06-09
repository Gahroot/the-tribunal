"""add call_payments table for in-call payment/deposit collection

Revision ID: 20260610_call_payments
Revises: 20260609_phone_messages
Create Date: 2026-06-10

Adds the ``call_payments`` table that backs the ``collect_payment`` voice tool:
a Stripe Checkout Session is created for the requested amount and the secure
payment link is texted to the caller (no raw card numbers over the AI channel).
Each attempt is recorded here, linked to the call's message + conversation,
the contact, and an optional opportunity/deal, with payment intent/status so
operators can track deposits and be notified on success.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260610_call_payments"
down_revision: str | Sequence[str] | None = "20260609_phone_messages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the call_payments table."""
    op.create_table(
        "call_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("contact_id", sa.BigInteger(), nullable=True),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("stripe_checkout_session_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_payment_intent_id", sa.String(length=255), nullable=True),
        sa.Column("payment_link_url", sa.Text(), nullable=True),
        sa.Column("sms_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("operators_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_call_payments_workspace_id"), "call_payments", ["workspace_id"]
    )
    op.create_index(op.f("ix_call_payments_message_id"), "call_payments", ["message_id"])
    op.create_index(
        op.f("ix_call_payments_conversation_id"), "call_payments", ["conversation_id"]
    )
    op.create_index(op.f("ix_call_payments_contact_id"), "call_payments", ["contact_id"])
    op.create_index(
        op.f("ix_call_payments_opportunity_id"), "call_payments", ["opportunity_id"]
    )
    op.create_index(op.f("ix_call_payments_agent_id"), "call_payments", ["agent_id"])
    op.create_index(op.f("ix_call_payments_status"), "call_payments", ["status"])
    op.create_index(
        op.f("ix_call_payments_stripe_checkout_session_id"),
        "call_payments",
        ["stripe_checkout_session_id"],
    )
    op.create_index(op.f("ix_call_payments_created_at"), "call_payments", ["created_at"])


def downgrade() -> None:
    """Drop the call_payments table."""
    op.drop_index(op.f("ix_call_payments_created_at"), table_name="call_payments")
    op.drop_index(
        op.f("ix_call_payments_stripe_checkout_session_id"), table_name="call_payments"
    )
    op.drop_index(op.f("ix_call_payments_status"), table_name="call_payments")
    op.drop_index(op.f("ix_call_payments_agent_id"), table_name="call_payments")
    op.drop_index(op.f("ix_call_payments_opportunity_id"), table_name="call_payments")
    op.drop_index(op.f("ix_call_payments_contact_id"), table_name="call_payments")
    op.drop_index(op.f("ix_call_payments_conversation_id"), table_name="call_payments")
    op.drop_index(op.f("ix_call_payments_message_id"), table_name="call_payments")
    op.drop_index(op.f("ix_call_payments_workspace_id"), table_name="call_payments")
    op.drop_table("call_payments")
