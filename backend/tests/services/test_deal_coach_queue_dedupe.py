"""Regression coverage for Deal Coach pending-action dedupe."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.pending_action import PendingAction
from app.schemas.deal_coach import DealCoachCard, DealSignals, DraftedAction, NextBestAction
from app.services.opportunities.deal_coach_service import DealCoachService

pytestmark = pytest.mark.asyncio

WS_ID = uuid.uuid4()
OPP_ID = uuid.uuid4()
ACTION_ID = uuid.uuid4()


def _make_card(body: str = "Hi Jane, checking in — want me to send next steps?") -> DealCoachCard:
    return DealCoachCard(
        opportunity_id=OPP_ID,
        workspace_id=WS_ID,
        name="Acme Expansion",
        amount=12000.0,
        currency="USD",
        primary_contact_id=42,
        contact_name="Jane Doe",
        deal_health="watch",
        health_score=65,
        health_summary="Watch — champion has gone quiet.",
        top_risk="No contact in 7 days",
        risk_factors=["No contact in 7 days"],
        next_best_action=NextBestAction(
            title="Re-engage the silent champion",
            rationale="Waiting on a reply.",
            channel="sms",
            timing="Today",
        ),
        drafted_action=DraftedAction(
            action_type="deal_coach.follow_up",
            channel="sms",
            description="Drafted re-engagement SMS to Jane Doe.",
            body=body,
            payload={"channel": "sms", "body": body},
        ),
        signals=DealSignals(days_since_last_contact=7, awaiting_reply=True),
        generated_by="heuristic",
        generated_at=datetime.now(UTC),
    )


async def test_queue_drafted_action_stores_stable_dedupe_key() -> None:
    db = AsyncMock()
    miss_result = MagicMock()
    miss_result.scalar_one_or_none.return_value = None
    db.execute.return_value = miss_result

    service = DealCoachService(db)
    service.coach_opportunity = AsyncMock(return_value=_make_card())  # type: ignore[method-assign]

    with patch(
        "app.services.approval.approval_gate_service.approval_gate_service.check_and_execute_or_queue",
        new=AsyncMock(
            return_value=(
                "pending",
                {"action_id": str(ACTION_ID), "description": "Drafted re-engagement SMS"},
            )
        ),
    ) as gate_mock:
        decision, action_id, action_type, description = await service.queue_drafted_action(
            WS_ID,
            OPP_ID,
        )

    assert decision == "pending"
    assert action_id == ACTION_ID
    assert action_type == "deal_coach.follow_up"
    assert description == "Drafted re-engagement SMS to Jane Doe."

    context = gate_mock.await_args.kwargs["context"]
    assert context["dedupe_key"].startswith("deal_coach.follow_up:")
    assert context["opportunity_id"] == str(OPP_ID)
    assert gate_mock.await_args.kwargs["action_payload"]["body"] == _make_card().drafted_action.body


async def test_queue_drafted_action_reuses_existing_pending_action_for_same_draft() -> None:
    existing = PendingAction(
        id=ACTION_ID,
        workspace_id=WS_ID,
        agent_id=None,
        action_type="deal_coach.follow_up",
        action_payload={"body": "custom"},
        description="Existing drafted SMS",
        context={"dedupe_key": "deal_coach.follow_up:existing"},
        status="pending",
        urgency="normal",
    )
    db = AsyncMock()
    hit_result = MagicMock()
    hit_result.scalar_one_or_none.return_value = existing
    db.execute.return_value = hit_result

    service = DealCoachService(db)
    service.coach_opportunity = AsyncMock(return_value=_make_card("custom"))  # type: ignore[method-assign]

    with patch(
        "app.services.approval.approval_gate_service.approval_gate_service.check_and_execute_or_queue",
        new=AsyncMock(),
    ) as gate_mock:
        decision, action_id, action_type, description = await service.queue_drafted_action(
            WS_ID,
            OPP_ID,
            body="custom",
        )

    assert decision == "pending"
    assert action_id == ACTION_ID
    assert action_type == "deal_coach.follow_up"
    assert description == "Existing drafted SMS"
    gate_mock.assert_not_awaited()
