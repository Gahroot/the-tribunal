"""Tests for lead magnet opt-in delivery."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from tribunal_lead_capture import deliver_lead_magnet_to_lead
from tribunal_lead_capture import service as lead_magnet_delivery

from app.models.lead_magnet import DeliveryMethod, LeadMagnet, LeadMagnetType
from app.models.lead_magnet_lead import LeadMagnetLead
from app.models.workspace import Workspace


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(lead_magnet_delivery, "resolve_outbound_credentials", AsyncMock())
    session = AsyncMock()
    session.get.return_value = Workspace(
        name="Workspace name", settings={"business_name": "Brand A"}, is_active=True
    )
    return session


def _lead_magnet(**overrides: Any) -> LeadMagnet:
    values = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "name": "Seller Guide",
        "description": "A practical guide for listing your home.",
        "magnet_type": LeadMagnetType.PDF,
        "delivery_method": DeliveryMethod.EMAIL,
        "content_url": "https://cdn.example.com/seller-guide.pdf",
        "content_data": None,
        "is_active": True,
        "download_count": 0,
    }
    values.update(overrides)
    return LeadMagnet(**values)


def _lead(**overrides: Any) -> LeadMagnetLead:
    values = {
        "id": uuid4(),
        "lead_magnet_id": uuid4(),
        "workspace_id": uuid4(),
        "email": "lead@example.com",
        "name": "Pat Buyer",
        "delivered": False,
    }
    values.update(overrides)
    return LeadMagnetLead(**values)


async def test_deliver_lead_magnet_sends_email_and_marks_delivered(
    monkeypatch: pytest.MonkeyPatch,
    db,
) -> None:
    sent: dict[str, Any] = {}

    async def fake_send_automation_email(**kwargs: Any) -> bool:
        sent.update(kwargs)
        return True

    monkeypatch.setattr(
        lead_magnet_delivery,
        "send_automation_email",
        fake_send_automation_email,
    )
    lead = _lead()
    magnet = _lead_magnet(id=lead.lead_magnet_id, workspace_id=lead.workspace_id)

    delivered = await deliver_lead_magnet_to_lead(
        lead=lead,
        lead_magnet=magnet,
        offer_name="Home Seller Launch Offer",
        db=db,
        workspace_id=lead.workspace_id,
    )

    assert delivered is True
    assert lead.delivered is True
    assert lead.delivered_at is not None
    assert lead.delivery_attempted_at is not None
    assert lead.delivery_error is None
    assert sent["to_email"] == "lead@example.com"
    assert sent["subject"] == "Your Seller Guide"
    assert sent["idempotency_key"] == lead.id
    assert "https://cdn.example.com/seller-guide.pdf" in sent["body"]
    assert "Home Seller Launch Offer" in sent["body"]
    assert "— Brand A" in sent["body"]
    assert "The Tribunal" not in sent["body"]
    assert "reply to this email" not in sent["body"]
    assert sent["workspace_id"] == lead.workspace_id
    assert sent["db"] is db


async def test_deliver_lead_magnet_does_not_resend_provider_accepted_asset(monkeypatch, db):
    magnet = _lead_magnet()
    accepted_at = datetime.now(UTC)
    lead = _lead(
        workspace_id=magnet.workspace_id,
        lead_magnet_id=magnet.id,
        delivered=True,
        delivered_at=accepted_at,
    )
    send = AsyncMock()
    monkeypatch.setattr(lead_magnet_delivery, "send_automation_email", send)
    assert await deliver_lead_magnet_to_lead(
        lead=lead,
        lead_magnet=magnet,
        offer_name="Fixture",
        db=db,
        workspace_id=magnet.workspace_id,
    )
    send.assert_not_awaited()
    db.get.assert_not_awaited()
    assert lead.delivered_at == accepted_at


async def test_deliver_lead_magnet_records_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
    db,
) -> None:
    async def fake_send_automation_email(**kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(
        lead_magnet_delivery,
        "send_automation_email",
        fake_send_automation_email,
    )
    lead = _lead()
    magnet = _lead_magnet(id=lead.lead_magnet_id, workspace_id=lead.workspace_id)

    delivered = await deliver_lead_magnet_to_lead(
        lead=lead,
        lead_magnet=magnet,
        offer_name="Home Seller Launch Offer",
        db=db,
        workspace_id=lead.workspace_id,
    )

    assert delivered is False
    assert lead.delivered is False
    assert lead.delivered_at is None
    assert lead.delivery_attempted_at is not None
    assert (
        lead.delivery_error
        == "Email delivery service did not confirm acceptance of the lead magnet email."
    )


async def test_deliver_lead_magnet_records_missing_email_without_sending(
    monkeypatch: pytest.MonkeyPatch,
    db,
) -> None:
    async def unexpected_send_automation_email(**kwargs: Any) -> bool:
        raise AssertionError("email should not be sent without a recipient")

    monkeypatch.setattr(
        lead_magnet_delivery,
        "send_automation_email",
        unexpected_send_automation_email,
    )
    lead = _lead(email=None)
    magnet = _lead_magnet(id=lead.lead_magnet_id, workspace_id=lead.workspace_id)

    delivered = await deliver_lead_magnet_to_lead(
        lead=lead,
        lead_magnet=magnet,
        offer_name="Home Seller Launch Offer",
        db=db,
        workspace_id=lead.workspace_id,
    )

    assert delivered is False
    assert lead.delivered is False
    assert lead.delivered_at is None
    assert lead.delivery_attempted_at is not None
    assert lead.delivery_error == "No email address was provided for lead magnet delivery."


@pytest.mark.parametrize("mismatch", ["brand", "magnet"])
async def test_delivery_rejects_cross_brand_or_wrong_magnet(monkeypatch, db, mismatch):
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(lead_magnet_delivery, "send_automation_email", send)
    lead = _lead()
    magnet = _lead_magnet(
        id=lead.lead_magnet_id if mismatch == "brand" else uuid4(),
        workspace_id=uuid4() if mismatch == "brand" else lead.workspace_id,
    )
    assert not await deliver_lead_magnet_to_lead(
        lead=lead,
        lead_magnet=magnet,
        offer_name="Offer",
        db=db,
        workspace_id=lead.workspace_id,
    )
    send.assert_not_awaited()
    db.get.assert_not_awaited()
    assert lead.delivery_error == "Lead magnet does not belong to this brand."
