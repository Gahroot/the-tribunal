"""CRM assistant Stripe checkout / iMessage close coverage."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.call_payment import CallPayment, CallPaymentStatus
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.services.ai.crm_assistant._payment_tools import PaymentAssistantTools
from app.services.ai.crm_assistant._tool_context import CRMToolContext
from app.services.outbound.delivery import (
    OutboundDeliveryChannel,
    OutboundDeliveryResult,
    OutboundDeliveryStatus,
)


class _ExecuteResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalar_one_or_none(self) -> Any | None:
        return self._rows[0] if self._rows else None


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


def _contact(workspace_id: uuid.UUID) -> Contact:
    return Contact(
        id=101,
        workspace_id=workspace_id,
        first_name="Ava",
        last_name="Rivera",
        phone_number="+1555000101",
        phone_hash="phone-hash",
        email="ava@example.com",
        email_hash="email-hash",
        status="new",
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
        updated_at=datetime(2026, 5, 2, tzinfo=UTC),
    )


def _conversation(workspace_id: uuid.UUID) -> Conversation:
    return Conversation(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        contact_id=101,
        workspace_phone="+1555000999",
        contact_phone="+1555000101",
    )


def _db(workspace_id: uuid.UUID, *, conversation: Conversation | None) -> MagicMock:
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ExecuteResult([_contact(workspace_id)]),
            _ExecuteResult([conversation] if conversation else []),
        ]
    )
    return db


def _patch_payment_stack(
    monkeypatch: pytest.MonkeyPatch,
    *,
    delivered: bool = True,
) -> dict[str, Any]:
    from app.services.ai.crm_assistant import _payment_tools

    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        _payment_tools.call_payment_service, "is_payment_configured", lambda: True
    )

    async def fake_session(**kwargs: Any) -> Any:
        captured["session_kwargs"] = kwargs
        result = MagicMock()
        result.session_id = "cs_test_123"
        result.url = "https://checkout.stripe.com/c/pay/cs_test_123"
        result.payment_intent_id = "pi_test_123"
        return result

    monkeypatch.setattr(
        _payment_tools.call_payment_service,
        "create_payment_checkout_session",
        fake_session,
    )

    async def fake_deliver(db: Any, request: Any) -> OutboundDeliveryResult:
        captured["deliver_request"] = request
        message = MagicMock()
        message.id = uuid.uuid4()
        return OutboundDeliveryResult(
            channel=request.channel,
            status=(
                OutboundDeliveryStatus.SENT if delivered else OutboundDeliveryStatus.FAILED
            ),
            provider="mac_relay",
            message=message,
            reason=None if delivered else "imessage_failed",
        )

    monkeypatch.setattr(
        _payment_tools.outbound_delivery_service, "deliver", fake_deliver
    )
    return captured


async def test_create_checkout_link_closes_anchor_pack_over_imessage(
    workspace_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation = _conversation(workspace_id)
    db = _db(workspace_id, conversation=conversation)
    captured = _patch_payment_stack(monkeypatch)
    tools = PaymentAssistantTools(CRMToolContext(db=db, workspace_id=workspace_id, user_id=7))

    result = await tools.create_checkout_link({"pack_key": "anchor_500", "contact_id": 101})

    assert result["success"] is True
    assert result["amount"] == 2500.0
    assert result["checkout_url"].startswith("https://checkout.stripe.com/")

    # Stripe boundary is reused with the in-call payment metadata so the shared
    # billing webhook can reconcile + notify operators (no duplicated path).
    metadata = captured["session_kwargs"]["metadata"]
    assert metadata["kind"] == "in_call_payment"
    assert metadata["pack_key"] == "anchor_500"
    assert metadata["workspace_id"] == str(workspace_id)
    assert "call_payment_id" in metadata

    # Persisted a pending CallPayment row keyed for webhook reconcile.
    payment = db.add.call_args.args[0]
    assert isinstance(payment, CallPayment)
    assert payment.amount == 2500.0
    assert payment.stripe_checkout_session_id == "cs_test_123"
    assert payment.conversation_id == conversation.id

    # Delivered the link over iMessage from the conversation's workspace handle.
    request = captured["deliver_request"]
    assert request.channel is OutboundDeliveryChannel.IMESSAGE
    assert request.to == "+1555000101"
    assert request.from_ == "+1555000999"
    assert "checkout.stripe.com" in request.body


@pytest.mark.parametrize(
    ("pack_key", "expected"),
    [
        ("sampler_100", 497.0),
        ("growth_300", 1497.0),
        ("scale_1000", 3997.0),
    ],
)
async def test_create_checkout_link_uses_server_side_pack_price(
    workspace_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
    pack_key: str,
    expected: float,
) -> None:
    db = _db(workspace_id, conversation=_conversation(workspace_id))
    _patch_payment_stack(monkeypatch)
    tools = PaymentAssistantTools(CRMToolContext(db=db, workspace_id=workspace_id, user_id=7))

    result = await tools.create_checkout_link({"pack_key": pack_key, "contact_id": 101})

    assert result["success"] is True
    assert result["amount"] == expected


async def test_create_checkout_link_rejects_non_batch_pack(
    workspace_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _db(workspace_id, conversation=_conversation(workspace_id))
    _patch_payment_stack(monkeypatch)
    tools = PaymentAssistantTools(CRMToolContext(db=db, workspace_id=workspace_id, user_id=7))

    result = await tools.create_checkout_link({"pack_key": "ad_management", "contact_id": 101})

    assert result["success"] is False
    assert "escalated to a human" in result["error"]
    db.add.assert_not_called()


async def test_create_checkout_link_reports_imessage_delivery_failure(
    workspace_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _db(workspace_id, conversation=_conversation(workspace_id))
    _patch_payment_stack(monkeypatch, delivered=False)
    tools = PaymentAssistantTools(CRMToolContext(db=db, workspace_id=workspace_id, user_id=7))

    result = await tools.create_checkout_link({"pack_key": "anchor_500", "contact_id": 101})

    assert result["success"] is False
    assert "couldn't text it" in result["error"]
    assert result["checkout_url"].startswith("https://checkout.stripe.com/")
    payment = db.add.call_args.args[0]
    assert payment.status == CallPaymentStatus.PENDING


async def test_create_checkout_link_requires_existing_imessage_thread(
    workspace_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _db(workspace_id, conversation=None)
    _patch_payment_stack(monkeypatch)
    tools = PaymentAssistantTools(CRMToolContext(db=db, workspace_id=workspace_id, user_id=7))

    result = await tools.create_checkout_link({"pack_key": "anchor_500", "contact_id": 101})

    assert result["success"] is False
    assert "iMessage thread" in result["error"]
