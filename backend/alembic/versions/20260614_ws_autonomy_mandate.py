"""add workspace autonomy mandate

Revision ID: 20260614_ws_autonomy_mandate
Revises: 20260614_offer_ladder_strategy
Create Date: 2026-06-14 12:00:00.000000

"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260614_ws_autonomy_mandate"
down_revision: str | None = "20260614_offer_ladder_strategy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DEFAULT_MANDATE = {
    "version": 1,
    "enabled": True,
    "posture": "act_and_report",
    "auto_send_first_touches": True,
    "auto_close_batch_packs": True,
    "default_offer_id": None,
    "batch_pack_anchor_key": "anchor_500",
    "batch_pack_max_price_cents": 399700,
    "allowed_batch_packs": [
        {"pack_key": "sampler_100", "label": "100 ads", "ad_count": 100, "price_cents": 49700},
        {"pack_key": "growth_300", "label": "300 ads", "ad_count": 300, "price_cents": 149700},
        {"pack_key": "anchor_500", "label": "500 ads", "ad_count": 500, "price_cents": 250000},
        {"pack_key": "scale_1000", "label": "1,000 ads", "ad_count": 1000, "price_cents": 399700},
    ],
    "daily_send_cap": 100,
    "quiet_hours": {
        "enabled": True,
        "timezone": "America/New_York",
        "start": "20:00",
        "end": "08:00",
    },
    "escalation_rules": [
        {
            "key": "ad_management",
            "label": "Buyer wants ad-management / media buying / someone to run ads",
            "keywords": [
                "run ads",
                "manage ads",
                "media buying",
                "ad management",
                "campaign setup",
            ],
        },
        {
            "key": "ai_agent_install",
            "label": "Buyer wants AI-agent installation or automation buildout",
            "keywords": [
                "install ai",
                "ai agent",
                "set up an agent",
                "automation build",
                "chatbot",
            ],
        },
        {
            "key": "consulting",
            "label": "Buyer wants consulting or custom services beyond the batch",
            "keywords": [
                "consulting",
                "done for you",
                "strategy call",
                "custom service",
                "coach me",
            ],
        },
    ],
    "operator_report": {
        "enabled": True,
        "channel": "sms",
        "phone": None,
        "events": ["payment_succeeded", "human_escalation"],
    },
}


PRESTYJ_MANDATE = {
    **DEFAULT_MANDATE,
    "description": (
        "Autonomously run Prestyj Batch Video Ads sales over iMessage: discover, "
        "first-touch, objection-handle, anchor-close, Stripe payment, and report."
    ),
    "operator_report": {
        **DEFAULT_MANDATE["operator_report"],
        "phone": "+14155551997",
    },
}


def upgrade() -> None:
    default_json = json.dumps(DEFAULT_MANDATE)
    op.add_column(
        "workspaces",
        sa.Column(
            "autonomy_mandate",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text(f"'{default_json}'::jsonb"),
        ),
    )
    op.alter_column("workspaces", "autonomy_mandate", server_default=None)

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE workspaces
            SET autonomy_mandate = CAST(:mandate AS jsonb)
            WHERE slug = 'prestyj-batch-video-ads-demo'
            """
        ),
        {"mandate": json.dumps(PRESTYJ_MANDATE)},
    )


def downgrade() -> None:
    op.drop_column("workspaces", "autonomy_mandate")
