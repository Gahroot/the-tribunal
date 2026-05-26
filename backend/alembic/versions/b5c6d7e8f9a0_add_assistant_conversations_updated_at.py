"""Add missing ``updated_at`` column to ``assistant_conversations``.

The ``AssistantConversation`` ORM model declares ``updated_at`` (NOT NULL,
with ``onupdate=now()``), but the original migration
``a9b0c1d2e3f4_add_assistant_conversation_tables`` never created the column.
Every SELECT against the table therefore fails with
``column assistant_conversations.updated_at does not exist``, which surfaces
in the frontend as the "We couldn't load the assistant" error boundary.

This migration backfills the column on existing rows using ``created_at`` so
the NOT NULL constraint holds without a default sweep.

Revision ID: b5c6d7e8f9a0
Revises: dev01a1b2c3d4
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b5c6d7e8f9a0"
down_revision: str | Sequence[str] | None = "dev01a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _assistant_conversations_has_updated_at() -> bool:
    result = op.get_bind().execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'assistant_conversations'
              AND column_name = 'updated_at'
            LIMIT 1
            """
        )
    ).scalar_one_or_none()
    return result is not None


def upgrade() -> None:
    # Add as nullable first so existing rows can be backfilled, then enforce
    # NOT NULL once every row has a value.
    if not _assistant_conversations_has_updated_at():
        op.add_column(
            "assistant_conversations",
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=True,
                server_default=sa.func.now(),
            ),
        )
    op.execute(
        "UPDATE assistant_conversations SET updated_at = created_at "
        "WHERE updated_at IS NULL"
    )
    op.alter_column("assistant_conversations", "updated_at", nullable=False)


def downgrade() -> None:
    if _assistant_conversations_has_updated_at():
        op.drop_column("assistant_conversations", "updated_at")
