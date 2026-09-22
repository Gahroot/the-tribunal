"""add per-agent realtime_model and reasoning_effort for the GPT Live agent type

Revision ID: 20260709_agent_realtime_model
Revises: 20260615_message_traces
Create Date: 2026-07-09 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260709_agent_realtime_model"
down_revision: str | None = "20260615_message_traces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Per-agent OpenAI Realtime model. NULL => use the global default
    # (settings.openai_realtime_model). The "GPT Live" agent type stores
    # "gpt-realtime-2.1".
    op.add_column(
        "agents",
        sa.Column("realtime_model", sa.String(length=60), nullable=True),
    )
    # Reasoning effort for reasoning-capable Realtime models (gpt-realtime-2.x):
    # minimal | low | medium | high | xhigh. Defaults to "low".
    op.add_column(
        "agents",
        sa.Column(
            "reasoning_effort",
            sa.String(length=10),
            nullable=False,
            server_default="low",
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "reasoning_effort")
    op.drop_column("agents", "realtime_model")
