"""Add message tests tables for A/B testing outreach messages.

Revision ID: m7n8o9p0q1r2
Revises: l6m7n8o9p0q1
Create Date: 2026-01-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m7n8o9p0q1r2"
down_revision: str | None = "l6m7n8o9p0q1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create message_tests table
    op.create_table(
        "message_tests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("agent_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("from_phone_number", sa.String(length=50), nullable=False),
        sa.Column("use_number_pool", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("ai_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("qualification_criteria", sa.Text(), nullable=True),
        sa.Column("sending_hours_start", sa.Time(), nullable=True),
        sa.Column("sending_hours_end", sa.Time(), nullable=True),
        sa.Column("sending_days", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column("timezone", sa.String(length=50), nullable=False, server_default="America/New_York"),
        sa.Column("messages_per_minute", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("total_contacts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_variants", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("messages_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("replies_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contacts_qualified", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("winning_variant_id", sa.UUID(), nullable=True),
        sa.Column("converted_to_campaign_id", sa.UUID(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["converted_to_campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_message_tests_workspace_id", "message_tests", ["workspace_id"])
    op.create_index("ix_message_tests_agent_id", "message_tests", ["agent_id"])
    op.create_index("ix_message_tests_status", "message_tests", ["status"])

    # Create test_variants table
    op.create_table(
        "test_variants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("message_test_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("message_template", sa.Text(), nullable=False),
        sa.Column("is_control", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contacts_assigned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("messages_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("replies_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contacts_qualified", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("response_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("qualification_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["message_test_id"], ["message_tests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_test_variants_message_test_id", "test_variants", ["message_test_id"])

    # Add foreign key for winning_variant_id now that test_variants exists
    op.create_foreign_key(
        "fk_message_tests_winning_variant_id",
        "message_tests",
        "test_variants",
        ["winning_variant_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Create test_contacts table
    op.create_table(
        "test_contacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("message_test_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.BigInteger(), nullable=False),
        sa.Column("variant_id", sa.UUID(), nullable=True),
        sa.Column("conversation_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("is_qualified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("qualification_notes", sa.Text(), nullable=True),
        sa.Column("opted_out", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("opted_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reply_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("variant_assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["message_test_id"], ["message_tests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["variant_id"], ["test_variants.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_test_id", "contact_id", name="uq_test_contact"),
    )
    op.create_index("ix_test_contacts_message_test_id", "test_contacts", ["message_test_id"])
    op.create_index("ix_test_contacts_contact_id", "test_contacts", ["contact_id"])
    op.create_index("ix_test_contacts_variant_id", "test_contacts", ["variant_id"])
    op.create_index("ix_test_contacts_conversation_id", "test_contacts", ["conversation_id"])
    op.create_index("ix_test_contacts_status", "test_contacts", ["status"])


def downgrade() -> None:
    op.drop_table("test_contacts")
    op.drop_constraint("fk_message_tests_winning_variant_id", "message_tests", type_="foreignkey")
    op.drop_table("test_variants")
    op.drop_table("message_tests")
