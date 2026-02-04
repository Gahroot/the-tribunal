"""Add prompt instrumentation layer tables.

Creates tables for:
- prompt_versions: Immutable snapshots of agent prompts for attribution
- call_outcomes: Structured call outcome tracking with attribution
- call_feedback: User and automated feedback collection
- prompt_version_stats: Daily aggregated metrics per prompt version

Also adds prompt_version_id FK to messages table.

Revision ID: u5v6w7x8y9z0
Revises: t4u5v6w7x8y9
Create Date: 2026-02-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "u5v6w7x8y9z0"
down_revision: str | None = "t4u5v6w7x8y9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create prompt_versions table
    op.create_table(
        "prompt_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("initial_greeting", sa.Text(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_baseline", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("parent_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("total_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("successful_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("booked_appointments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["parent_version_id"], ["prompt_versions.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_prompt_versions_agent_id", "prompt_versions", ["agent_id"], unique=False
    )
    op.create_index(
        "ix_prompt_versions_is_active", "prompt_versions", ["is_active"], unique=False
    )

    # Create call_outcomes table
    op.create_table(
        "call_outcomes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("outcome_type", sa.String(50), nullable=False),
        sa.Column("signals", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "classified_by", sa.String(50), nullable=False, server_default="'hangup_cause'"
        ),
        sa.Column("classification_confidence", sa.Float(), nullable=True),
        sa.Column("raw_hangup_cause", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["prompt_version_id"], ["prompt_versions.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_call_outcomes_message_id", "call_outcomes", ["message_id"], unique=True
    )
    op.create_index(
        "ix_call_outcomes_prompt_version_id",
        "call_outcomes",
        ["prompt_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_call_outcomes_outcome_type", "call_outcomes", ["outcome_type"], unique=False
    )

    # Create call_feedback table
    op.create_table(
        "call_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("call_outcome_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("thumbs", sa.String(10), nullable=True),
        sa.Column("feedback_text", sa.Text(), nullable=True),
        sa.Column(
            "feedback_signals", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("quality_reasoning", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["call_outcome_id"], ["call_outcomes.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_call_feedback_message_id", "call_feedback", ["message_id"], unique=False
    )
    op.create_index(
        "ix_call_feedback_call_outcome_id",
        "call_feedback",
        ["call_outcome_id"],
        unique=False,
    )
    op.create_index(
        "ix_call_feedback_source", "call_feedback", ["source"], unique=False
    )

    # Create prompt_version_stats table
    op.create_table(
        "prompt_version_stats",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column("total_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "appointments_booked", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("leads_qualified", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("no_answer_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("voicemail_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_duration_seconds", sa.Float(), nullable=True),
        sa.Column(
            "total_duration_seconds", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("avg_quality_score", sa.Float(), nullable=True),
        sa.Column("feedback_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "positive_feedback_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("booking_rate", sa.Float(), nullable=True),
        sa.Column("qualification_rate", sa.Float(), nullable=True),
        sa.Column("completion_rate", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["prompt_version_id"], ["prompt_versions.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "prompt_version_id", "stat_date", name="uq_prompt_version_stats_date"
        ),
    )
    op.create_index(
        "ix_prompt_version_stats_prompt_version_id",
        "prompt_version_stats",
        ["prompt_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_prompt_version_stats_stat_date",
        "prompt_version_stats",
        ["stat_date"],
        unique=False,
    )

    # Add prompt_version_id FK to messages table
    op.add_column(
        "messages",
        sa.Column("prompt_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_messages_prompt_version_id",
        "messages",
        ["prompt_version_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_messages_prompt_version_id",
        "messages",
        "prompt_versions",
        ["prompt_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Drop FK from messages
    op.drop_constraint("fk_messages_prompt_version_id", "messages", type_="foreignkey")
    op.drop_index("ix_messages_prompt_version_id", table_name="messages")
    op.drop_column("messages", "prompt_version_id")

    # Drop prompt_version_stats table
    op.drop_index(
        "ix_prompt_version_stats_stat_date", table_name="prompt_version_stats"
    )
    op.drop_index(
        "ix_prompt_version_stats_prompt_version_id", table_name="prompt_version_stats"
    )
    op.drop_table("prompt_version_stats")

    # Drop call_feedback table
    op.drop_index("ix_call_feedback_source", table_name="call_feedback")
    op.drop_index("ix_call_feedback_call_outcome_id", table_name="call_feedback")
    op.drop_index("ix_call_feedback_message_id", table_name="call_feedback")
    op.drop_table("call_feedback")

    # Drop call_outcomes table
    op.drop_index("ix_call_outcomes_outcome_type", table_name="call_outcomes")
    op.drop_index("ix_call_outcomes_prompt_version_id", table_name="call_outcomes")
    op.drop_index("ix_call_outcomes_message_id", table_name="call_outcomes")
    op.drop_table("call_outcomes")

    # Drop prompt_versions table
    op.drop_index("ix_prompt_versions_is_active", table_name="prompt_versions")
    op.drop_index("ix_prompt_versions_agent_id", table_name="prompt_versions")
    op.drop_table("prompt_versions")
