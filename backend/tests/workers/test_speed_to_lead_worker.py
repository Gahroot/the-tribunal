"""Unit tests for the speed-to-lead instant first-touch worker."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.models.contact import Contact
from app.models.workspace import Workspace
from app.services.sla import speed_to_lead as stl
from app.workers import speed_to_lead_worker as stlw
from app.workers.base import BaseWorker
from app.workers.retryable import RetryableWorker
from app.workers.speed_to_lead_worker import SpeedToLeadWorker


def test_class_config() -> None:
    """Worker wires into the shared base/retryable classes with a fast poll."""
    assert issubclass(SpeedToLeadWorker, RetryableWorker)
    assert issubclass(SpeedToLeadWorker, BaseWorker)
    assert SpeedToLeadWorker.COMPONENT_NAME == "speed_to_lead_worker"
    assert SpeedToLeadWorker.max_retries == 3
    assert SpeedToLeadWorker.POLL_INTERVAL_SECONDS <= 10


def test_normalize_first_touch_channels() -> None:
    """Channel lists are deduped, filtered to known values, order preserved."""
    assert stl.normalize_first_touch_channels(["voice", "sms", "voice"]) == ("voice", "sms")
    assert stl.normalize_first_touch_channels(["sms"]) == ("sms",)
    assert stl.normalize_first_touch_channels([]) == ()
    # Junk payloads fall back to the default channel pair.
    assert stl.normalize_first_touch_channels("junk") == stl.DEFAULT_FIRST_TOUCH_CHANNELS
    assert stl.normalize_first_touch_channels(None) == stl.DEFAULT_FIRST_TOUCH_CHANNELS


def test_build_speed_to_lead_job_roundtrip() -> None:
    """Jobs serialize with the shape the worker parses back."""
    workspace_id = uuid.uuid4()
    job = stl.build_speed_to_lead_job(workspace_id, 42, source="lead_form")
    assert job == {
        "workspace_id": str(workspace_id),
        "contact_id": 42,
        "source": "lead_form",
        "channels": ["voice", "sms"],
        "attempts": 0,
    }


def _workspace(speed_to_lead: dict | None = None, mandate: dict | None = None) -> Workspace:
    return Workspace(
        name="Test WS",
        settings={"speed_to_lead": speed_to_lead or {}},
        autonomy_mandate=mandate or {},
    )


def _contact(*, phone_number: str = "+15550001111") -> Contact:
    return Contact(
        workspace_id=uuid.uuid4(),
        first_name="Ada",
        phone_number=phone_number,
    )


def test_config_gate_blocks_disabled_workspace() -> None:
    workspace = _workspace(speed_to_lead={"enabled": False})
    assert stlw.config_gate(workspace, _contact()) == "speed_to_lead_disabled"


def test_config_gate_blocks_off_mandate() -> None:
    workspace = _workspace(mandate={"enabled": True, "auto_send_first_touches": False})
    assert stlw.config_gate(workspace, _contact()) == "autonomy_mandate_blocks_first_touch"


def test_config_gate_requires_telnyx_key() -> None:
    with patch.object(settings, "telnyx_api_key", ""):
        assert stlw.config_gate(_workspace(), _contact()) == "telnyx_not_configured"


def test_config_gate_allows_configured_workspace() -> None:
    with patch.object(settings, "telnyx_api_key", "test-key"):
        assert stlw.config_gate(_workspace(), _contact()) is None


def test_quiet_hours_config_defaults() -> None:
    """A fresh workspace carries the mandate's default quiet hours."""
    quiet = stlw.quiet_hours_config(_workspace())
    assert quiet.get("enabled") is True
    assert quiet.get("start") == "20:00"
    assert quiet.get("end") == "08:00"
    assert quiet.get("timezone") == "America/New_York"


def test_build_compliance_campaign_injects_quiet_hours() -> None:
    quiet = stlw.quiet_hours_config(_workspace())
    campaign = stlw.build_compliance_campaign(uuid.uuid4(), quiet)
    assert campaign.quiet_hours_start == time(20, 0)
    assert campaign.quiet_hours_end == time(8, 0)
    assert campaign.quiet_hours_timezone == "America/New_York"

    # Quiet hours disabled → evaluator's start/end guard short-circuits open.
    open_campaign = stlw.build_compliance_campaign(uuid.uuid4(), {"enabled": False})
    assert open_campaign.quiet_hours_start is None
    assert open_campaign.quiet_hours_end is None


def test_next_quiet_hours_end_defers_to_morning() -> None:
    quiet = stlw.quiet_hours_config(_workspace())
    # 11:00 UTC on a Wednesday = 19:00 in New York (EDT): after 20:00? No —
    # 19:00 is before the 20:00 window, but the helper only cares about the
    # *end* time: the next 08:00 local after 19:00 is tomorrow morning.
    now = datetime(2026, 9, 23, 23, 0, tzinfo=UTC)  # 19:00 EDT
    run_at = stlw.next_quiet_hours_end(quiet, now)
    assert run_at is not None
    assert run_at.hour == 8
    assert run_at > now


def test_next_quiet_hours_end_same_day_when_before_end() -> None:
    quiet = stlw.quiet_hours_config(_workspace())
    # 03:00 UTC = 23:00 EDT the previous evening: next 08:00 is that same
    # (already-rolled) morning, still ahead of local now.
    now = datetime(2026, 9, 24, 7, 0, tzinfo=UTC)  # 03:00 EDT
    run_at = stlw.next_quiet_hours_end(quiet, now)
    assert run_at is not None
    assert run_at.hour == 8
    assert run_at > now


def test_next_quiet_hours_end_none_when_disabled() -> None:
    assert stlw.next_quiet_hours_end({"enabled": False}, datetime.now(UTC)) is None
    assert stlw.next_quiet_hours_end({}, datetime.now(UTC)) is None
    assert stlw.next_quiet_hours_end({"enabled": True, "end": "junk"}, datetime.now(UTC)) is None


def test_action_for_channel() -> None:
    assert stlw.action_for_channel("voice") == "speed_to_lead.voice_dial"
    assert stlw.action_for_channel("sms") == "speed_to_lead.first_touch_sms"


def test_owned_by_quiet_hours() -> None:
    quiet = MagicMock(allowed=False, reason="quiet_hours")
    other = MagicMock(allowed=False, reason="global_opt_out")
    assert stlw.owned_by_quiet_hours({"voice": quiet, "sms": quiet}) is True
    assert stlw.owned_by_quiet_hours({"voice": quiet, "sms": other}) is False
    assert stlw.owned_by_quiet_hours({}) is False


def test_as_int_swallows_junk() -> None:
    assert stlw._as_int(None) == 0
    assert stlw._as_int("junk") == 0
    assert stlw._as_int("3") == 3


@pytest.mark.asyncio
async def test_enqueue_job_pushes_json_onto_queue() -> None:
    redis = MagicMock()
    redis.rpush = AsyncMock()
    workspace_id = uuid.uuid4()
    with patch.object(stl, "get_redis", new=AsyncMock(return_value=redis)):
        ok = await stl.enqueue_speed_to_lead_job(
            workspace_id, 7, source="lead_form", channels=("voice",)
        )
    assert ok is True
    redis.rpush.assert_awaited_once()
    key, payload = redis.rpush.await_args.args
    assert key == stl.QUEUE_KEY
    job = json.loads(payload)
    assert job["workspace_id"] == str(workspace_id)
    assert job["contact_id"] == 7
    assert job["channels"] == ["voice"]


@pytest.mark.asyncio
async def test_enqueue_job_never_raises_when_redis_down() -> None:
    broken = AsyncMock(side_effect=RuntimeError("redis down"))
    with patch.object(stl, "get_redis", new=broken):
        ok = await stl.enqueue_speed_to_lead_job(uuid.uuid4(), 7, source="lead_form")
    assert ok is False


@pytest.mark.asyncio
async def test_drain_jobs_parses_and_tolerates_bad_rows() -> None:
    good = {"workspace_id": str(uuid.uuid4()), "contact_id": 9, "channels": ["voice"]}
    redis = MagicMock()
    redis.lpop = AsyncMock(return_value=[json.dumps(good), "not-json", json.dumps(["nope"])])
    worker = SpeedToLeadWorker()
    with patch.object(stlw, "get_redis", new=AsyncMock(return_value=redis)):
        jobs = await worker._drain_jobs()
    redis.lpop.assert_awaited_once_with(stl.QUEUE_KEY, worker.BATCH_SIZE)
    assert jobs == [good]


@pytest.mark.asyncio
async def test_drain_jobs_returns_empty_on_redis_failure() -> None:
    redis = MagicMock()
    redis.lpop = AsyncMock(side_effect=RuntimeError("redis down"))
    worker = SpeedToLeadWorker()
    with patch.object(stlw, "get_redis", new=AsyncMock(return_value=redis)):
        assert await worker._drain_jobs() == []


@pytest.mark.asyncio
async def test_promote_delayed_jobs_moves_due_payloads_onto_queue() -> None:
    payload = json.dumps({"workspace_id": str(uuid.uuid4()), "contact_id": 1})
    redis = MagicMock()
    redis.zrangebyscore = AsyncMock(return_value=[payload])
    redis.zrem = AsyncMock(return_value=1)
    redis.rpush = AsyncMock()
    worker = SpeedToLeadWorker()
    with patch.object(stlw, "get_redis", new=AsyncMock(return_value=redis)):
        await worker._promote_delayed_jobs()
    redis.zrem.assert_awaited_once_with(stl.DELAYED_QUEUE_KEY, payload)
    redis.rpush.assert_awaited_once_with(stl.QUEUE_KEY, payload)


@pytest.mark.asyncio
async def test_promote_delayed_jobs_skips_payloads_still_waiting() -> None:
    payload = json.dumps({"workspace_id": str(uuid.uuid4()), "contact_id": 1})
    redis = MagicMock()
    redis.zrangebyscore = AsyncMock(return_value=[payload])
    redis.zrem = AsyncMock(return_value=0)  # lost the race; another worker took it
    redis.rpush = AsyncMock()
    worker = SpeedToLeadWorker()
    with patch.object(stlw, "get_redis", new=AsyncMock(return_value=redis)):
        await worker._promote_delayed_jobs()
    redis.rpush.assert_not_awaited()
