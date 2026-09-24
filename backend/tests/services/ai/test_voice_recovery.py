"""Provider failures flow to bounded callbacks, not silent calls or repeat SMS."""

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.campaign import CampaignContactStatus, CampaignStatus
from app.services.ai.elevenlabs_voice_agent import ElevenLabsVoiceAgentSession
from app.services.ai.grok import GrokVoiceAgentSession
from app.services.ai.voice_agent import VoiceAgentSession
from app.services.ai.voice_health import VoiceProviderError, event_failure_reason
from app.services.campaigns import voice_recovery as recovery
from app.services.outbound.delivery import OutboundDeliveryChannel, OutboundDeliveryStatus
from app.websockets import voice_bridge as bridge
from app.workers.voice_campaign_worker import VoiceCampaignWorker


@pytest.mark.parametrize("code", ["rate_limit_exceeded", "insufficient_quota", "server_error"])
def test_fatal_events(code: str) -> None:
    assert event_failure_reason({"type": "error", "error": {"code": code}})
    assert event_failure_reason({"type": "response.done", "response": {"status": "failed"}})


@pytest.mark.parametrize(
    "event",
    [
        {"type": "error", "error": {"code": "response_cancel_not_active"}},
        {"type": "response.done", "response": {"status": "cancelled"}},
        {"type": "rate_limits.updated", "rate_limits": [{"remaining": 0}]},
    ],
)
def test_recoverable_events_do_not_kill_call(event: dict) -> None:
    assert event_failure_reason(event) is None


class EventSocket:
    def __aiter__(self):
        return self.events()

    async def events(self):
        yield json.dumps({"type": "error", "error": {"code": "rate_limit_exceeded"}})
        await asyncio.Event().wait()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cls", [VoiceAgentSession, GrokVoiceAgentSession, ElevenLabsVoiceAgentSession]
)
async def test_real_provider_receive_loop_surfaces_rate_limit(cls, monkeypatch) -> None:
    session = cls("test-key", "test-key") if cls is ElevenLabsVoiceAgentSession else cls("test-key")
    if cls is ElevenLabsVoiceAgentSession:
        session.grok_ws = EventSocket()
        await asyncio.wait_for(session._receive_from_grok(), 1)
        assert await asyncio.wait_for(session._audio_queue.get(), 1) is None
    else:
        session.ws = EventSocket()
        chunks = [chunk async for chunk in session.receive_audio_stream()]
        assert chunks == []
    assert session.provider_failure_reason == "rate_limited"


@pytest.mark.asyncio
async def test_dead_elevenlabs_tts_unblocks_output() -> None:
    session = ElevenLabsVoiceAgentSession("test-key", "test-key")

    async def ended():
        if False:
            yield b""

    session._tts_session = SimpleNamespace(receive_audio_stream=ended)
    await session._receive_from_tts()
    assert await asyncio.wait_for(session._audio_queue.get(), 1) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("normal_hangup", [False, True])
async def test_relay_distinguishes_carrier_stop_from_provider_end(
    monkeypatch, normal_hangup
) -> None:
    async def ended(*args, **kwargs):
        return

    cancelled = asyncio.Event()

    async def waiting(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(
        bridge, "_receive_from_telnyx_and_send_to_provider", ended if normal_hangup else waiting
    )
    monkeypatch.setattr(
        bridge, "_receive_from_provider_and_send_to_telnyx", waiting if normal_hangup else ended
    )
    session = MagicMock()
    session.provider_failure_reason = "rate_limited"
    if normal_hangup:
        await bridge._relay_audio(MagicMock(), session, MagicMock())
    else:
        with pytest.raises(VoiceProviderError, match="rate_limited"):
            await bridge._relay_audio(MagicMock(), session, MagicMock())
    assert cancelled.is_set()


@pytest.fixture
def recovery_context(monkeypatch):
    workspace_id = uuid4()
    campaign = SimpleNamespace(
        id=uuid4(),
        workspace_id=workspace_id,
        status=CampaignStatus.RUNNING,
        timezone="UTC",
        sending_days=list(range(7)),
        sending_hours_start=None,
        sending_hours_end=None,
        from_phone_number="+12025550100",
        voice_agent_id=uuid4(),
        messages_sent=0,
    )
    entry = SimpleNamespace(
        id=uuid4(),
        contact_id=1,
        campaign=campaign,
        contact=SimpleNamespace(workspace_id=workspace_id, phone_number="+12025550101"),
        status=CampaignContactStatus.CALLING,
        opted_out=False,
        call_attempts=1,
        call_message_id=uuid4(),
        last_reply_at=None,
        last_call_at=datetime.now(UTC),
        last_call_status=None,
        last_error=None,
        next_follow_up_at=None,
        messages_sent=0,
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = entry
    result.scalar_one.return_value = entry
    db = AsyncMock()
    db.execute.return_value = result
    db.__aenter__.return_value = db
    monkeypatch.setattr(recovery, "AsyncSessionLocal", lambda: db)
    redis = AsyncMock()
    redis.get.return_value = str(int(time.time()))
    monkeypatch.setattr(recovery, "get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(recovery.OptOutManager, "check_opt_out", AsyncMock(return_value=False))
    delivery = AsyncMock(
        return_value=SimpleNamespace(delivered=True, status=OutboundDeliveryStatus.SENT)
    )
    monkeypatch.setattr(recovery.OutboundDeliveryService, "deliver", delivery)
    return workspace_id, campaign, entry, db, redis, delivery


@pytest.mark.asyncio
async def test_durable_retry_before_sms_and_duplicate_noop(recovery_context) -> None:
    workspace, campaign, entry, db, redis, delivery = recovery_context

    async def send(*args):
        assert db.commit.await_count == 1
        assert entry.status == CampaignContactStatus.PENDING
        assert entry.next_follow_up_at is not None
        return SimpleNamespace(delivered=True, status=OutboundDeliveryStatus.SENT)

    delivery.side_effect = send
    assert await recovery.recover_voice_call("call", workspace, "openai", "rate_limited")
    assert entry.call_attempts == 1
    assert entry.last_call_status == recovery.RECOVERY
    assert entry.messages_sent == campaign.messages_sent == 1
    request = delivery.await_args.args[1]
    assert request.require_sms_consent
    assert request.channel == OutboundDeliveryChannel.SMS
    assert request.workspace_id == workspace
    assert request.idempotency_parts == (entry.id, entry.call_message_id)
    assert not await recovery.recover_voice_call("call", workspace, "openai", "rate_limited")
    delivery.assert_awaited_once()
    redis.set.assert_awaited()
    sql = str(db.execute.await_args_list[0].args[0])
    assert "campaigns.workspace_id" in sql and "conversations.workspace_id" in sql
    assert "FOR UPDATE" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "blocked", ["opted_out", "wrong_workspace", "paused", "reply", "exhausted", "missing"]
)
async def test_recovery_never_revives_ineligible_contacts(recovery_context, blocked) -> None:
    workspace, campaign, entry, db, _, delivery = recovery_context
    if blocked == "opted_out":
        entry.opted_out = True
    elif blocked == "wrong_workspace":
        entry.contact.workspace_id = uuid4()
    elif blocked == "paused":
        campaign.status = CampaignStatus.PAUSED
    elif blocked == "reply":
        entry.last_reply_at = datetime.now(UTC)
    elif blocked == "exhausted":
        entry.call_attempts = recovery.MAX_CALL_ATTEMPTS
    else:
        db.execute.return_value.scalar_one_or_none.return_value = None
    assert not await recovery.recover_voice_call("call", workspace, "grok", "provider_error")
    assert entry.next_follow_up_at is None
    delivery.assert_not_awaited()


@pytest.mark.asyncio
async def test_sms_failure_keeps_durable_retry_for_worker(recovery_context) -> None:
    workspace, _, entry, db, _, delivery = recovery_context
    delivery.return_value = SimpleNamespace(delivered=False, status=OutboundDeliveryStatus.FAILED)
    assert await recovery.recover_voice_call("call", workspace, "elevenlabs", "provider_error")
    assert entry.status == CampaignContactStatus.PENDING
    assert entry.last_error == recovery.SMS_PENDING
    assert db.commit.await_count == 2


@pytest.mark.asyncio
async def test_sick_worker_uses_honest_message_and_keeps_retry(recovery_context) -> None:
    workspace, _, entry, _, redis, delivery = recovery_context
    redis.get.return_value = str(int(time.time()) - 600)
    assert await recovery.recover_voice_call("call", workspace, "openai", "provider_error")
    assert "2 minutes" not in delivery.await_args.args[1].body
    assert "when service is available" in delivery.await_args.args[1].body
    assert entry.status == CampaignContactStatus.PENDING


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [None, "bad", "0", str(int(time.time()) + 600)])
async def test_missing_malformed_stale_future_heartbeats_are_sick(monkeypatch, raw) -> None:
    redis = AsyncMock()
    redis.get.return_value = raw
    monkeypatch.setattr(recovery, "get_redis", AsyncMock(return_value=redis))
    assert not await recovery.callback_worker_healthy()


@pytest.mark.asyncio
async def test_redis_outage_defers_calls(monkeypatch) -> None:
    monkeypatch.setattr(recovery, "get_redis", AsyncMock(side_effect=ConnectionError))
    assert await recovery.provider_cooling_down(uuid4(), "grok")


def test_two_minute_slot_and_closed_hours(recovery_context) -> None:
    _, campaign, _, _, _, _ = recovery_context
    now = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
    assert recovery.retry_slot(campaign, now) == now + timedelta(minutes=2)
    late = now.replace(hour=23)
    assert recovery.retry_slot(campaign, late) > late + timedelta(minutes=2)


@pytest.mark.asyncio
async def test_recovery_retry_respects_new_optout(recovery_context, monkeypatch) -> None:
    _, campaign, entry, db, _, _ = recovery_context
    entry.last_call_status = recovery.RECOVERY
    monkeypatch.setattr(recovery.OptOutManager, "check_opt_out", AsyncMock(return_value=True))
    assert not await VoiceCampaignWorker._recovery_allows_call(campaign, entry, entry.contact, db)
    assert entry.status == CampaignContactStatus.OPTED_OUT


def test_recovery_is_not_delayed_by_two_hour_sms_cadence(recovery_context) -> None:
    _, campaign, entry, _, _, _ = recovery_context
    entry.last_call_status = recovery.RECOVERY
    assert not VoiceCampaignWorker()._defer_call_for_sms(campaign, entry, None)


def test_rate_limited_dial_requeues_without_counting_a_call(recovery_context) -> None:
    _, campaign, entry, _, _, _ = recovery_context
    entry.status = CampaignContactStatus.PENDING
    message = SimpleNamespace(status="failed", error_code="RATE_LIMITED")
    assert not VoiceCampaignWorker._record_started_call(campaign, entry, message)
    assert entry.status == CampaignContactStatus.PENDING
    assert entry.call_attempts == 1
    assert entry.next_follow_up_at is not None
    assert entry.last_error == "voice_recovery:rate_limited"


@pytest.mark.asyncio
async def test_healthy_worker_promises_two_minutes(recovery_context, monkeypatch) -> None:
    workspace, _, _, _, _, delivery = recovery_context
    monkeypatch.setattr(recovery, "retry_slot", lambda campaign, now: now + timedelta(seconds=120))
    await recovery.recover_voice_call("call", workspace, "openai", "rate_limited")
    assert "call you back in 2 minutes" in delivery.await_args.args[1].body


@pytest.mark.asyncio
async def test_late_hangup_does_not_override_recovery(recovery_context) -> None:
    from app.services.campaigns.campaign_call_stats import update_campaign_call_stats

    _, _, entry, db, _, _ = recovery_context
    entry.status = CampaignContactStatus.PENDING
    entry.last_call_status = recovery.RECOVERY
    entry.next_follow_up_at = datetime.now(UTC) + timedelta(seconds=120)
    due = entry.next_follow_up_at
    await update_campaign_call_stats(
        db, entry.call_message_id, "voicemail", "completed", 5, MagicMock()
    )
    assert entry.last_call_status == recovery.RECOVERY
    assert entry.next_follow_up_at == due
    db.commit.assert_not_awaited()
