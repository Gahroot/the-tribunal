"""caller memory (persistent cross-call memory)

Revision ID: 20260610_caller_memory
Revises: 20260610_call_payments
Create Date: 2026-06-10 00:00:00.000000

Adds the ``caller_memories`` table: one embedded summary per completed call,
scoped to ``workspace_id`` + ``contact_id``. Powers returning-caller recall by
letting future calls retrieve prior conversational context (chronologically or
semantically via the ``vector(1536)`` embedding) rather than only CRM fields.
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260610_caller_memory"
down_revision: str | Sequence[str] | None = "20260610_call_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgvector extension is already installed by the RAG chunks migration, but
    # guard idempotently so this migration is safe to run standalone.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "caller_memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_id", sa.BigInteger(), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=True),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(1536), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_caller_memories_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contacts.id"],
            name=op.f("fk_caller_memories_contact_id_contacts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_caller_memories_conversation_id_conversations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_caller_memories_message_id_messages"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_caller_memories")),
    )
    op.create_index(
        op.f("ix_caller_memories_workspace_id"),
        "caller_memories",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_caller_memories_contact_id"),
        "caller_memories",
        ["contact_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_caller_memories_message_id"),
        "caller_memories",
        ["message_id"],
        unique=False,
    )
    # Hot path: list a caller's memories newest-first, scoped to tenant + contact.
    op.create_index(
        "ix_caller_memories_workspace_contact_occurred",
        "caller_memories",
        ["workspace_id", "contact_id", sa.text("occurred_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_caller_memories_workspace_contact_occurred", table_name="caller_memories"
    )
    op.drop_index(op.f("ix_caller_memories_message_id"), table_name="caller_memories")
    op.drop_index(op.f("ix_caller_memories_contact_id"), table_name="caller_memories")
    op.drop_index(op.f("ix_caller_memories_workspace_id"), table_name="caller_memories")
    op.drop_table("caller_memories")
    # Leave the ``vector`` extension installed; other objects rely on it.
