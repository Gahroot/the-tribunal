"""Add campaign_reports table.

Revision ID: a1b2c3d4e5f6
Revises: z8a9b0c1d2e3
Create Date: 2026-02-05 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "z8a9b0c1d2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaign_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="generating"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metrics_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("executive_summary", sa.Text(), nullable=True),
        sa.Column("key_findings", postgresql.JSONB(), nullable=True),
        sa.Column("what_worked", postgresql.JSONB(), nullable=True),
        sa.Column("what_didnt_work", postgresql.JSONB(), nullable=True),
        sa.Column("recommendations", postgresql.JSONB(), nullable=True),
        sa.Column("segment_analysis", postgresql.JSONB(), nullable=True),
        sa.Column("timing_analysis", postgresql.JSONB(), nullable=True),
        sa.Column("prompt_performance", postgresql.JSONB(), nullable=True),
        sa.Column("generated_suggestion_ids", postgresql.JSONB(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["campaigns.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("campaign_id", name="uq_campaign_reports_campaign_id"),
    )
    op.create_index("ix_campaign_reports_workspace_id", "campaign_reports", ["workspace_id"])
    op.create_index("ix_campaign_reports_campaign_id", "campaign_reports", ["campaign_id"])
    op.create_index("ix_campaign_reports_status", "campaign_reports", ["status"])
    op.create_index("ix_campaign_reports_created_at", "campaign_reports", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_campaign_reports_created_at", table_name="campaign_reports")
    op.drop_index("ix_campaign_reports_status", table_name="campaign_reports")
    op.drop_index("ix_campaign_reports_campaign_id", table_name="campaign_reports")
    op.drop_index("ix_campaign_reports_workspace_id", table_name="campaign_reports")
    op.drop_table("campaign_reports")
