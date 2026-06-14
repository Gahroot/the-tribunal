"""Tests for lead magnet opt-in delivery."""

from typing import Any
from uuid import uuid4

import pytest

from app.models.lead_magnet import DeliveryMethod, LeadMagnet, LeadMagnetType
from app.models.lead_magnet_lead import LeadMagnetLead
from app.services import lead_magnet_delivery
from app.services.lead_magnet_delivery import deliver_lead_magnet_to_lead


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
    magnet = _lead_magnet(id=lead.lead_magnet_id)

    delivered = await deliver_lead_magnet_to_lead(
        lead=lead,
        lead_magnet=magnet,
        offer_name="Home Seller Launch Offer",
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


async def test_deliver_lead_magnet_records_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_send_automation_email(**kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(
        lead_magnet_delivery,
        "send_automation_email",
        fake_send_automation_email,
    )
    lead = _lead()
    magnet = _lead_magnet(id=lead.lead_magnet_id)

    delivered = await deliver_lead_magnet_to_lead(
        lead=lead,
        lead_magnet=magnet,
        offer_name="Home Seller Launch Offer",
    )

    assert delivered is False
    assert lead.delivered is False
    assert lead.delivered_at is None
    assert lead.delivery_attempted_at is not None
    assert lead.delivery_error == "Email delivery service did not accept the lead magnet email."


async def test_deliver_lead_magnet_records_missing_email_without_sending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unexpected_send_automation_email(**kwargs: Any) -> bool:
        raise AssertionError("email should not be sent without a recipient")

    monkeypatch.setattr(
        lead_magnet_delivery,
        "send_automation_email",
        unexpected_send_automation_email,
    )
    lead = _lead(email=None)
    magnet = _lead_magnet(id=lead.lead_magnet_id)

    delivered = await deliver_lead_magnet_to_lead(
        lead=lead,
        lead_magnet=magnet,
        offer_name="Home Seller Launch Offer",
    )

    assert delivered is False
    assert lead.delivered is False
    assert lead.delivered_at is None
    assert lead.delivery_attempted_at is not None
    assert lead.delivery_error == "No email address was provided for lead magnet delivery."
