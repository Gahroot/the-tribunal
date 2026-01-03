"""Add SMS compliance and rate limiting.

This migration adds:
1. Phone number reputation tracking fields
2. Phone number daily statistics table
3. Global opt-out table
4. Campaign number pool table
5. Message bounce tracking fields
6. Campaign number pool flag

Revision ID: f1a2b3c4d5e6
Revises: e5fe47013c85
Create Date: 2026-01-03 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "e5fe47013c85"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # === 1. Add reputation fields to phone_numbers table ===
    # Trust tier configuration
    op.add_column(
        "phone_numbers",
        sa.Column("trust_tier", sa.String(50), nullable=False, server_default="low_volume"),
    )
    op.add_column(
        "phone_numbers",
        sa.Column("daily_limit", sa.Integer(), nullable=False, server_default="75"),
    )
    op.add_column(
        "phone_numbers",
        sa.Column("hourly_limit", sa.Integer(), nullable=False, server_default="10"),
    )
    op.add_column(
        "phone_numbers",
        sa.Column("messages_per_second", sa.Float(), nullable=False, server_default="1.0"),
    )

    # Health status
    op.add_column(
        "phone_numbers",
        sa.Column("health_status", sa.String(50), nullable=False, server_default="healthy"),
    )
    op.create_index("ix_phone_numbers_health_status", "phone_numbers", ["health_status"])

    # 7-day rolling metrics
    op.add_column(
        "phone_numbers",
        sa.Column("messages_sent_7d", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "phone_numbers",
        sa.Column("messages_delivered_7d", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "phone_numbers",
        sa.Column("hard_bounces_7d", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "phone_numbers",
        sa.Column("soft_bounces_7d", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "phone_numbers",
        sa.Column("spam_complaints_7d", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "phone_numbers",
        sa.Column("opt_outs_7d", sa.Integer(), nullable=False, server_default="0"),
    )

    # Calculated rates
    op.add_column(
        "phone_numbers",
        sa.Column("delivery_rate", sa.Float(), nullable=False, server_default="0.0"),
    )
    op.add_column(
        "phone_numbers",
        sa.Column("bounce_rate", sa.Float(), nullable=False, server_default="0.0"),
    )
    op.add_column(
        "phone_numbers",
        sa.Column("complaint_rate", sa.Float(), nullable=False, server_default="0.0"),
    )

    # Warming schedule
    op.add_column(
        "phone_numbers",
        sa.Column("warming_stage", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "phone_numbers",
        sa.Column("warming_started_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Quarantine tracking
    op.add_column(
        "phone_numbers",
        sa.Column("quarantined_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "phone_numbers",
        sa.Column("quarantine_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "phone_numbers",
        sa.Column("quarantine_reviewed", sa.Boolean(), nullable=False, server_default="false"),
    )

    # Last send tracking
    op.add_column(
        "phone_numbers",
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
    )

    # === 2. Create phone_number_daily_stats table ===
    op.create_table(
        "phone_number_daily_stats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "phone_number_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("phone_numbers.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("date", sa.Date(), nullable=False, index=True),
        sa.Column("messages_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("messages_delivered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("messages_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hard_bounces", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("soft_bounces", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("spam_complaints", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("opt_outs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("phone_number_id", "date", name="uq_phone_daily_stats"),
    )

    # === 3. Create global_opt_outs table ===
    op.create_table(
        "global_opt_outs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("phone_number", sa.String(50), nullable=False, index=True),
        sa.Column(
            "opted_out_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("opt_out_keyword", sa.String(50), nullable=True),
        sa.Column("source_campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("workspace_id", "phone_number", name="uq_workspace_opt_out"),
    )

    # === 4. Create campaign_number_pools table ===
    op.create_table(
        "campaign_number_pools",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "phone_number_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("phone_numbers.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("messages_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "campaign_id", "phone_number_id", name="uq_campaign_phone_number_pool"
        ),
    )

    # === 5. Add bounce fields to messages table ===
    op.add_column(
        "messages",
        sa.Column("bounce_type", sa.String(50), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("bounce_category", sa.String(100), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("carrier_error_code", sa.String(50), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("carrier_name", sa.String(100), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column(
            "from_phone_number_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("phone_numbers.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_messages_from_phone_number_id", "messages", ["from_phone_number_id"]
    )

    # === 6. Add use_number_pool to campaigns table ===
    op.add_column(
        "campaigns",
        sa.Column("use_number_pool", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    # === 6. Remove use_number_pool from campaigns ===
    op.drop_column("campaigns", "use_number_pool")

    # === 5. Remove bounce fields from messages ===
    op.drop_index("ix_messages_from_phone_number_id", table_name="messages")
    op.drop_column("messages", "from_phone_number_id")
    op.drop_column("messages", "carrier_name")
    op.drop_column("messages", "carrier_error_code")
    op.drop_column("messages", "bounce_category")
    op.drop_column("messages", "bounce_type")

    # === 4. Drop campaign_number_pools table ===
    op.drop_table("campaign_number_pools")

    # === 3. Drop global_opt_outs table ===
    op.drop_table("global_opt_outs")

    # === 2. Drop phone_number_daily_stats table ===
    op.drop_table("phone_number_daily_stats")

    # === 1. Remove reputation fields from phone_numbers ===
    op.drop_column("phone_numbers", "last_sent_at")
    op.drop_column("phone_numbers", "quarantine_reviewed")
    op.drop_column("phone_numbers", "quarantine_reason")
    op.drop_column("phone_numbers", "quarantined_at")
    op.drop_column("phone_numbers", "warming_started_at")
    op.drop_column("phone_numbers", "warming_stage")
    op.drop_column("phone_numbers", "complaint_rate")
    op.drop_column("phone_numbers", "bounce_rate")
    op.drop_column("phone_numbers", "delivery_rate")
    op.drop_column("phone_numbers", "opt_outs_7d")
    op.drop_column("phone_numbers", "spam_complaints_7d")
    op.drop_column("phone_numbers", "soft_bounces_7d")
    op.drop_column("phone_numbers", "hard_bounces_7d")
    op.drop_column("phone_numbers", "messages_delivered_7d")
    op.drop_column("phone_numbers", "messages_sent_7d")
    op.drop_index("ix_phone_numbers_health_status", table_name="phone_numbers")
    op.drop_column("phone_numbers", "health_status")
    op.drop_column("phone_numbers", "messages_per_second")
    op.drop_column("phone_numbers", "hourly_limit")
    op.drop_column("phone_numbers", "daily_limit")
    op.drop_column("phone_numbers", "trust_tier")
