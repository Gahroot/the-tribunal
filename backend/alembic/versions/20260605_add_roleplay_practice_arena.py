"""add practice-arena roleplay tables

Revision ID: 20260605_roleplay_arena
Revises: b546d7e401fe
Create Date: 2026-06-05

Adds the user-facing practice arena: synthetic prospect personas and scored
rehearsal runs so operators can rehearse an AI agent (or a human rep) against
believable prospects before touching real leads.

- prospect_personas: reusable synthetic prospects. NULL workspace_id => built-in
  template shared across workspaces; non-null => workspace-owned custom persona.
- rehearsal_runs: one scored rehearsal (transcript + report).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260605_roleplay_arena"
down_revision: str | Sequence[str] | None = "b546d7e401fe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create prospect_personas and rehearsal_runs tables."""
    op.create_table(
        "prospect_personas",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("difficulty", sa.String(length=20), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("persona_prompt", sa.Text(), nullable=False),
        sa.Column("opening_message", sa.Text(), nullable=True),
        sa.Column("objections", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("is_builtin", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_prospect_personas_workspace_id"),
        "prospect_personas",
        ["workspace_id"],
    )
    op.create_index(
        op.f("ix_prospect_personas_slug"),
        "prospect_personas",
        ["slug"],
    )

    op.create_table(
        "rehearsal_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("persona_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_name", sa.String(length=200), nullable=True),
        sa.Column("persona_name", sa.String(length=200), nullable=True),
        sa.Column("rehearsee", sa.String(length=10), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("max_turns", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("transcript", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scores", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=True),
        sa.Column("objection_coverage", sa.Float(), nullable=True),
        sa.Column("booking_attempted", sa.Boolean(), nullable=True),
        sa.Column("tone_score", sa.Float(), nullable=True),
        sa.Column("strengths", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("gaps", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("suggestions", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["persona_id"], ["prospect_personas.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_rehearsal_runs_workspace_id"), "rehearsal_runs", ["workspace_id"])
    op.create_index(op.f("ix_rehearsal_runs_agent_id"), "rehearsal_runs", ["agent_id"])
    op.create_index(op.f("ix_rehearsal_runs_persona_id"), "rehearsal_runs", ["persona_id"])
    op.create_index(op.f("ix_rehearsal_runs_status"), "rehearsal_runs", ["status"])


def downgrade() -> None:
    """Drop the practice-arena tables."""
    op.drop_index(op.f("ix_rehearsal_runs_status"), table_name="rehearsal_runs")
    op.drop_index(op.f("ix_rehearsal_runs_persona_id"), table_name="rehearsal_runs")
    op.drop_index(op.f("ix_rehearsal_runs_agent_id"), table_name="rehearsal_runs")
    op.drop_index(op.f("ix_rehearsal_runs_workspace_id"), table_name="rehearsal_runs")
    op.drop_table("rehearsal_runs")

    op.drop_index(op.f("ix_prospect_personas_slug"), table_name="prospect_personas")
    op.drop_index(op.f("ix_prospect_personas_workspace_id"), table_name="prospect_personas")
    op.drop_table("prospect_personas")
