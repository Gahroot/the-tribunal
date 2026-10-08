"""Campaign worker iMessage sender routing tests."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.campaign import CampaignContactStatus
from app.models.conversation import Message, MessageChannel, MessageStatus
from app.workers.campaign_worker import CampaignWorker
from tests.factories import (
    CampaignContactFactory,
    CampaignFactory,
    ContactFactory,
    PhoneNumberFactory,
)


class _ScalarsResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class _ExecuteResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> _ScalarsResult:
        return _ScalarsResult(self._rows)

    def scalar_one_or_none(self) -> object | None:
        # Workspace.autonomy_mandate lookup. Return an explicitly disabled
        # mandate so these routing-focused tests genuinely skip the first-touch
        # tracing path (a None here would normalize to the *default* mandate,
        # which has autonomy ON).
        return {"enabled": False, "auto_send_first_touches": False}


def test_provider_cache_is_scoped_by_brand() -> None:
    worker = CampaignWorker()
    cache = {}
    phones = [
        PhoneNumberFactory.build(workspace_id=uuid.uuid4(), imessage_enabled=False)
        for _ in range(2)
    ]
    providers = [MagicMock(), MagicMock()]
    with patch(
        "app.workers.campaign_worker.get_text_message_provider", side_effect=providers
    ) as factory:
        assert worker._get_text_provider(phones[0], cache) is providers[0]
        assert worker._get_text_provider(phones[1], cache) is providers[1]
        assert worker._get_text_provider(phones[0], cache) is providers[0]
    assert factory.call_count == 2
    assert len(cache) == 2


async def test_initial_message_uses_mac_relay_for_imessage_sender() -> None:
    workspace_id = uuid.uuid4()
    campaign = CampaignFactory.build(
        workspace_id=workspace_id,
        from_phone_number="+15551230000",
        initial_message="Hi {first_name}",
    )
    contact = ContactFactory.build(
        id=123,
        workspace_id=workspace_id,
        first_name="Ava",
        phone_number="+15559870000",
    )
    campaign_contact = CampaignContactFactory.build(
        campaign=campaign,
        campaign_id=campaign.id,
        contact=contact,
        contact_id=contact.id,
        status=CampaignContactStatus.PENDING,
    )
    from_phone = PhoneNumberFactory.build(
        workspace_id=workspace_id,
        phone_number="+15551230000",
        imessage_enabled=True,
        mac_relay_sender_id="owner@example.com",
        mac_relay_service="imessage",
    )
    outbound_message = Message(
        id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        direction="outbound",
        channel=MessageChannel.IMESSAGE,
        body="Hi Ava",
        status=MessageStatus.SENT,
    )
    text_service = AsyncMock()
    text_service.send_message = AsyncMock(return_value=outbound_message)

    worker = CampaignWorker()
    worker.rate_limiter.check_campaign_rate_limit = AsyncMock(return_value=True)
    worker.number_pool.peek_next_available_number = AsyncMock(return_value=from_phone)
    worker.number_pool.reserve_number_for_send = AsyncMock(return_value=True)
    worker.compliance_service.evaluate = AsyncMock(
        return_value=MagicMock(allowed=True, reason=None)
    )
    worker.compliance_service.apply_suppression = MagicMock()
    worker.reputation_tracker.increment_sent = AsyncMock()

    db = MagicMock()
    db.execute = AsyncMock(return_value=_ExecuteResult([campaign_contact]))
    db.flush = AsyncMock()

    with patch(
        "app.workers.campaign_worker.get_text_message_provider",
        MagicMock(return_value=text_service),
    ) as get_provider:
        await worker._process_initial_messages(campaign, {}, db, MagicMock())

    get_provider.assert_called_once_with("mac_relay", mac_relay_service="imessage")
    text_service.send_message.assert_awaited_once()
    send_kwargs = text_service.send_message.await_args.kwargs
    assert send_kwargs["to_number"] == contact.phone_number
    assert send_kwargs["from_number"] == "owner@example.com"
    assert send_kwargs["phone_number_id"] == from_phone.id
    assert campaign_contact.status == CampaignContactStatus.SENT
    assert campaign_contact.conversation_id == outbound_message.conversation_id
    assert campaign.messages_sent == 1
    worker.compliance_service.evaluate.assert_awaited_once()
    compliance_request = worker.compliance_service.evaluate.await_args.args[0]
    assert compliance_request.channel == "imessage"
    assert compliance_request.action_type == "campaign_initial_imessage"


async def test_initial_message_uses_telnyx_for_sms_sender() -> None:
    workspace_id = uuid.uuid4()
    campaign = CampaignFactory.build(workspace_id=workspace_id, initial_message="Hi {first_name}")
    contact = ContactFactory.build(id=124, workspace_id=workspace_id, first_name="Sam")
    campaign_contact = CampaignContactFactory.build(
        campaign=campaign,
        campaign_id=campaign.id,
        contact=contact,
        contact_id=contact.id,
        status=CampaignContactStatus.PENDING,
    )
    from_phone = PhoneNumberFactory.build(
        workspace_id=workspace_id,
        imessage_enabled=False,
        mac_relay_sender_id="owner@example.com",
    )
    outbound_message = Message(
        id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        direction="outbound",
        channel=MessageChannel.SMS,
        body="Hi Sam",
        status=MessageStatus.SENT,
    )
    text_service = AsyncMock()
    text_service.send_message = AsyncMock(return_value=outbound_message)

    worker = CampaignWorker()
    worker.rate_limiter.check_campaign_rate_limit = AsyncMock(return_value=True)
    worker.number_pool.peek_next_available_number = AsyncMock(return_value=from_phone)
    worker.number_pool.reserve_number_for_send = AsyncMock(return_value=True)
    worker.compliance_service.evaluate = AsyncMock(
        return_value=MagicMock(allowed=True, reason=None)
    )
    worker.compliance_service.apply_suppression = MagicMock()
    worker.reputation_tracker.increment_sent = AsyncMock()

    db = MagicMock()
    db.execute = AsyncMock(return_value=_ExecuteResult([campaign_contact]))
    db.flush = AsyncMock()

    with patch(
        "app.workers.campaign_worker.get_text_message_provider",
        MagicMock(return_value=text_service),
    ) as get_provider:
        await worker._process_initial_messages(campaign, {}, db, MagicMock())

    get_provider.assert_called_once_with(None, mac_relay_service=None)
    send_kwargs = text_service.send_message.await_args.kwargs
    assert send_kwargs["from_number"] == from_phone.phone_number
    compliance_request = worker.compliance_service.evaluate.await_args.args[0]
    assert compliance_request.channel == "sms"
    assert compliance_request.action_type == "campaign_initial_sms"


async def test_initial_send_rechecks_consent_and_excludes_without_sending() -> None:
    """Send-time recheck: consent withdrawn after launch → excluded, never sent."""
    from app.services.compliance.outbound_compliance import OutboundComplianceService

    workspace_id = uuid.uuid4()
    campaign = CampaignFactory.build(workspace_id=workspace_id, initial_message="Hi")
    contact = ContactFactory.build(id=125, workspace_id=workspace_id, sms_consent_status="unknown")
    campaign_contact = CampaignContactFactory.build(
        campaign=campaign,
        campaign_id=campaign.id,
        contact=contact,
        contact_id=contact.id,
        status=CampaignContactStatus.PENDING,
    )
    from_phone = PhoneNumberFactory.build(workspace_id=workspace_id, imessage_enabled=False)
    text_service = AsyncMock()

    worker = CampaignWorker()
    opt_out_manager = MagicMock()
    opt_out_manager.check_opt_out = AsyncMock(return_value=False)
    worker.compliance_service = OutboundComplianceService(opt_out_manager=opt_out_manager)
    worker.rate_limiter.check_campaign_rate_limit = AsyncMock(return_value=True)
    worker.number_pool.peek_next_available_number = AsyncMock(return_value=from_phone)
    worker.number_pool.reserve_number_for_send = AsyncMock(return_value=True)

    db = MagicMock()
    db.execute = AsyncMock(return_value=_ExecuteResult([campaign_contact]))
    db.flush = AsyncMock()

    with patch(
        "app.workers.campaign_worker.get_text_message_provider",
        MagicMock(return_value=text_service),
    ):
        await worker._process_initial_messages(campaign, {}, db, MagicMock())

    text_service.send_message.assert_not_called()
    worker.number_pool.reserve_number_for_send.assert_not_called()
    assert campaign_contact.status == CampaignContactStatus.EXCLUDED
    assert campaign_contact.suppressed_reason == "missing_sms_consent"
    assert campaign.messages_sent == 0
