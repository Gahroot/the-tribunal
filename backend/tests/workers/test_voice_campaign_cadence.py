"""The worker sends paced SMS before allowing the next voice touch."""

from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.models.campaign import CampaignContactStatus
from app.services.campaigns import sms_fallback
from app.workers import voice_campaign_worker as module


def _campaign() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        voice_agent=None,
        timezone="America/New_York",
        sending_days=list(range(7)),
        sending_hours_start=None,
        sending_hours_end=None,
        sms_fallback_enabled=True,
        sms_fallback_template="Hi",
        sms_fallback_use_ai=False,
        sms_fallback_agent_id=None,
        max_messages_per_contact=5,
        max_messages_per_campaign=None,
        messages_sent=0,
    )


def _entry(now: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        status=CampaignContactStatus.PENDING,
        opted_out=False,
        call_attempts=1,
        last_call_status="no_answer",
        last_call_at=now - timedelta(days=1),
        last_reply_at=None,
        sms_fallback_sent_at=None,
        messages_sent=0,
        next_follow_up_at=now,
        contact=SimpleNamespace(phone_number="+12025550123", last_engaged_at=None),
    )


@pytest.mark.asyncio
async def test_worker_sends_due_sms_then_defers_next_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    campaign = _campaign()
    entry = _entry(now)
    result = MagicMock()
    result.scalars.return_value = [entry]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    monkeypatch.setattr(module.settings, "telnyx_api_key", "test-key")
    monkeypatch.setattr(module, "approved_best_hour", AsyncMock(return_value=None))

    async def send(*args: object, **kwargs: object) -> bool:
        entry.sms_fallback_sent_at = datetime.now(UTC)
        return True

    send_mock = AsyncMock(side_effect=send)
    monkeypatch.setattr(sms_fallback, "send_sms_fallback", send_mock)

    worker = module.VoiceCampaignWorker()
    await worker._process_scheduled_sms(campaign, db, MagicMock())
    send_mock.assert_awaited_once()
    assert entry.next_follow_up_at >= entry.sms_fallback_sent_at + timedelta(hours=2)
    # The call is already safely scheduled; do not push it out a second time.
    scheduled = entry.next_follow_up_at
    assert not worker._defer_call_for_sms(campaign, entry, None)
    assert entry.next_follow_up_at == scheduled


@pytest.mark.asyncio
async def test_new_voice_attempt_clears_previous_voicemail_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    campaign = _campaign()
    campaign.sms_fallback_enabled = False
    campaign.calls_per_minute = 10
    campaign.voice_connection_id = None
    campaign.from_phone_number = "+12025550199"
    campaign.voice_agent_id = None
    campaign.enable_machine_detection = True
    campaign.calls_attempted = 1
    entry = _entry(now)
    entry.first_sent_at = now - timedelta(days=2)
    entry.last_call_status = "voicemail"
    entry.contact.id = 123
    entry.contact.phone_number = "+12025550123"
    result = MagicMock()
    result.scalars.return_value.all.return_value = [entry]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    voice = MagicMock()
    voice.initiate_call = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(module, "approved_best_hour", AsyncMock(return_value=None))
    monkeypatch.setattr(module, "provider_cooling_down", AsyncMock(return_value=False))

    await module.VoiceCampaignWorker()._process_pending_calls(campaign, voice, db, MagicMock())

    voice.initiate_call.assert_awaited_once()
    assert entry.status == CampaignContactStatus.CALLING
    assert entry.call_attempts == 2
    assert entry.last_call_status is None


@pytest.mark.asyncio
async def test_missing_hangup_preserves_detected_voicemail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    campaign = _campaign()
    campaign.calls_no_answer = 0
    entry = _entry(now)
    entry.status = CampaignContactStatus.CALLING
    entry.last_call_status = "voicemail"
    entry.first_sent_at = now - timedelta(minutes=6)
    entry.last_call_at = entry.first_sent_at
    result = MagicMock()
    result.scalars.return_value.all.return_value = [entry]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    monkeypatch.setattr(module, "approved_best_hour", AsyncMock(return_value=None))

    await module.VoiceCampaignWorker()._cleanup_stuck_calls(campaign, db, MagicMock())

    assert entry.last_call_status == "voicemail"
    assert entry.status == CampaignContactStatus.PENDING
    assert entry.next_follow_up_at >= now + timedelta(days=2)


@pytest.mark.asyncio
async def test_worker_does_not_send_before_scheduled_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    campaign = _campaign()
    campaign.sending_days = [(now.astimezone(ZoneInfo(campaign.timezone)).weekday() + 1) % 7]
    campaign.sending_hours_start = time(16)
    campaign.sending_hours_end = time(17)
    entry = _entry(now)
    # A failed call just over two hours ago may still wait until the next 4pm.
    entry.last_call_at = now - timedelta(hours=2, minutes=1)
    result = MagicMock()
    result.scalars.return_value = [entry]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    monkeypatch.setattr(module.settings, "telnyx_api_key", "test-key")
    monkeypatch.setattr(module, "approved_best_hour", AsyncMock(return_value=None))
    send_mock = AsyncMock()
    monkeypatch.setattr(sms_fallback, "send_sms_fallback", send_mock)

    await module.VoiceCampaignWorker()._process_scheduled_sms(
        campaign,
        db,
        MagicMock(),
    )
    assert module.sms_touch_due_at(campaign, entry) > datetime.now(UTC)
    send_mock.assert_not_awaited()
