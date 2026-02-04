"""Add improvement suggestions and auto-improve settings.

Adds:
- improvement_suggestions table for LLM-generated prompt improvement queue
- auto_suggest, auto_activate, auto_improve_min_calls to agents table

Revision ID: x8y9z0a1b2c3
Revises: w7x8y9z0a1b2
Create Date: 2026-02-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "x8y9z0a1b2c3"
down_revision: str | None = "w7x8y9z0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add auto-improvement settings to agents table
    op.add_column(
        "agents",
        sa.Column("auto_suggest", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "agents",
        sa.Column("auto_activate", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "agents",
        sa.Column(
            "auto_improve_min_calls",
            sa.Integer(),
            nullable=False,
            server_default="100",
        ),
    )

    # Create improvement_suggestions table
    op.create_table(
        "improvement_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "source_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        # The suggested improvement
        sa.Column("suggested_prompt", sa.Text(), nullable=False),
        sa.Column("suggested_greeting", sa.Text(), nullable=True),
        sa.Column("mutation_type", sa.String(50), nullable=False),
        # LLM analysis
        sa.Column("analysis_summary", sa.Text(), nullable=False),
        sa.Column("expected_improvement", sa.Text(), nullable=True),
        # Queue status
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_id", sa.Integer(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        # If approved, link to created version
        sa.Column(
            "created_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_version_id"], ["prompt_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_version_id"], ["prompt_versions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"], ["users.id"], ondelete="SET NULL"
        ),
    )

    # Create indexes
    op.create_index(
        "ix_improvement_suggestions_agent_id",
        "improvement_suggestions",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        "ix_improvement_suggestions_status",
        "improvement_suggestions",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_improvement_suggestions_created_at",
        "improvement_suggestions",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    # Drop improvement_suggestions table
    op.drop_index(
        "ix_improvement_suggestions_created_at",
        table_name="improvement_suggestions",
    )
    op.drop_index(
        "ix_improvement_suggestions_status",
        table_name="improvement_suggestions",
    )
    op.drop_index(
        "ix_improvement_suggestions_agent_id",
        table_name="improvement_suggestions",
    )
    op.drop_table("improvement_suggestions")

    # Drop agent columns
    op.drop_column("agents", "auto_improve_min_calls")
    op.drop_column("agents", "auto_activate")
    op.drop_column("agents", "auto_suggest")
