"""Add scoped task model policy; preserve existing per-agent voice selections.

Revision ID: 20260923_model_configs
Revises: 20260923_contact_timeline
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "20260923_model_configs"
down_revision = "20260923_contact_timeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("task", sa.String(40), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("input_usd_per_million", sa.Numeric(12, 6), nullable=True),
        sa.Column("output_usd_per_million", sa.Numeric(12, 6), nullable=True),
        sa.CheckConstraint(
            "task IN ('voice_llm', 'transcript_analysis', 'transcript_judgment', "
            "'caller_memory', 'prompt_improvement', 'reports')",
            name="ck_model_configs_task",
        ),
        sa.CheckConstraint("length(model) > 0", name="ck_model_configs_model"),
        sa.CheckConstraint(
            "(input_usd_per_million IS NULL AND output_usd_per_million IS NULL) OR "
            "(input_usd_per_million >= 0 AND output_usd_per_million >= 0)",
            name="ck_model_configs_prices",
        ),
    )
    op.create_index(
        "uq_model_configs_workspace_task",
        "model_configs",
        ["workspace_id", "task"],
        unique=True,
        postgresql_where=sa.text("agent_id IS NULL"),
    )
    op.create_index(
        "uq_model_configs_agent_task",
        "model_configs",
        ["agent_id", "task"],
        unique=True,
        postgresql_where=sa.text("agent_id IS NOT NULL"),
    )
    # Copy rather than drop the legacy field: older deployments and the existing
    # agent-edit UI can still read it while clients migrate to the new surface.
    op.execute(
        sa.text("""
        INSERT INTO model_configs (id, workspace_id, agent_id, task, model)
        SELECT gen_random_uuid(), workspace_id, id, 'voice_llm', realtime_model
        FROM agents WHERE realtime_model IS NOT NULL AND realtime_model <> ''
    """)
    )


def downgrade() -> None:
    op.drop_index("uq_model_configs_agent_task", table_name="model_configs")
    op.drop_index("uq_model_configs_workspace_task", table_name="model_configs")
    op.drop_table("model_configs")
