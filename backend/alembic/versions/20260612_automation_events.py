"""automation events queue + event-keyed executions

Revision ID: 20260612_automation_events
Revises: 20260611_bookable_staff
Create Date: 2026-06-12 00:00:00.000000

Expands the automation engine to event-based triggers:

- ``automation_events`` table: a durable queue of domain events
  (review_received, opportunity_created, deal_stage_changed, missed_call,
  roleplay_completed, knowledge_document_uploaded, …) emitted from services and
  drained by the automation worker.
- ``automation_executions`` gains a nullable ``event_id`` and ``contact_id``
  becomes nullable (events such as roleplay/knowledge have no contact). The old
  ``uq_automation_execution(automation_id, contact_id)`` constraint is replaced
  with two partial unique indexes so polling-trigger dedupe (per contact) and
  event-trigger dedupe (per event) coexist.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260612_automation_events"
down_revision: str | Sequence[str] | None = "20260611_bookable_staff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- automation_events queue --------------------------------------------
    op.create_table(
        "automation_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("contact_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_automation_events_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contacts.id"],
            name=op.f("fk_automation_events_contact_id_contacts"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_automation_events")),
    )
    op.create_index(
        op.f("ix_automation_events_workspace_id"),
        "automation_events",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_automation_events_event_type"),
        "automation_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_automation_events_contact_id"),
        "automation_events",
        ["contact_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_automation_events_status"),
        "automation_events",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_automation_events_status_created",
        "automation_events",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_automation_events_workspace_type",
        "automation_events",
        ["workspace_id", "event_type"],
        unique=False,
    )

    # --- automation_executions: event linkage + dedupe rework ---------------
    op.add_column(
        "automation_executions",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        op.f("ix_automation_executions_event_id"),
        "automation_executions",
        ["event_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_automation_executions_event_id_automation_events"),
        "automation_executions",
        "automation_events",
        ["event_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # contact_id becomes nullable (event-only executions have no contact).
    op.alter_column(
        "automation_executions",
        "contact_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )

    # Replace the single unique constraint with two partial unique indexes.
    op.drop_constraint(
        "uq_automation_execution",
        "automation_executions",
        type_="unique",
    )
    op.create_index(
        "uq_automation_execution_contact",
        "automation_executions",
        ["automation_id", "contact_id"],
        unique=True,
        postgresql_where=sa.text("event_id IS NULL"),
    )
    op.create_index(
        "uq_automation_execution_event",
        "automation_executions",
        ["automation_id", "event_id"],
        unique=True,
        postgresql_where=sa.text("event_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_automation_execution_event",
        table_name="automation_executions",
    )
    op.drop_index(
        "uq_automation_execution_contact",
        table_name="automation_executions",
    )
    op.create_unique_constraint(
        "uq_automation_execution",
        "automation_executions",
        ["automation_id", "contact_id"],
    )
    op.alter_column(
        "automation_executions",
        "contact_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.drop_constraint(
        op.f("fk_automation_executions_event_id_automation_events"),
        "automation_executions",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_automation_executions_event_id"),
        table_name="automation_executions",
    )
    op.drop_column("automation_executions", "event_id")

    op.drop_index(
        "ix_automation_events_workspace_type", table_name="automation_events"
    )
    op.drop_index(
        "ix_automation_events_status_created", table_name="automation_events"
    )
    op.drop_index(op.f("ix_automation_events_status"), table_name="automation_events")
    op.drop_index(op.f("ix_automation_events_contact_id"), table_name="automation_events")
    op.drop_index(op.f("ix_automation_events_event_type"), table_name="automation_events")
    op.drop_index(op.f("ix_automation_events_workspace_id"), table_name="automation_events")
    op.drop_table("automation_events")
