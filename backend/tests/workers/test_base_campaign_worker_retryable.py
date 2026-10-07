"""BaseCampaignWorker — RetryableWorker contract.

``BaseCampaignWorker`` is abstract; we instantiate a minimal concrete
subclass to exercise the mixin behavior.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import QueryableAttribute

import app.workers.base_campaign_worker as base_campaign_worker_module
from app.models.campaign import CampaignStatus, CampaignType
from app.schemas.campaign import CampaignCreate
from app.services.campaigns.cadence import next_local_slot
from app.workers.base import BaseWorker
from app.workers.base_campaign_worker import BaseCampaignWorker
from app.workers.retryable import RetryableWorker
from app.workers.voice_campaign_worker import VoiceCampaignWorker
from tests.workers._retryable_helpers import wire_worker_for_retry_test


class _StubCampaignWorker(BaseCampaignWorker):
    COMPONENT_NAME = "stub_campaign_worker"

    @property
    def campaign_type(self) -> CampaignType:
        return CampaignType.SMS

    @property
    def eager_loads(self) -> list[QueryableAttribute[Any]]:
        return []

    async def _process_campaign_contacts(self, campaign, db, log) -> None:  # type: ignore[no-untyped-def]
        return None

    def _get_remaining_filter(self, campaign):  # type: ignore[no-untyped-def]
        return None


def test_base_class_inherits_retryable_and_base() -> None:
    assert issubclass(BaseCampaignWorker, RetryableWorker)
    assert issubclass(BaseCampaignWorker, BaseWorker)


def test_retry_configuration_inherited_defaults() -> None:
    assert BaseCampaignWorker.max_retries == 3
    assert BaseCampaignWorker.backoff_base_seconds == 2.0


@pytest.mark.asyncio
async def test_failed_campaign_processing_routes_to_dlq() -> None:
    worker = _StubCampaignWorker()
    recorder = wire_worker_for_retry_test(worker)

    campaign = MagicMock(id=uuid4(), name="bad campaign")
    db = MagicMock()

    async def fail(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("campaign blew up")

    item_key = f"campaign:{campaign.id}"
    await worker.execute_with_retry(fail, campaign, db, item_key=item_key)

    assert len(recorder.calls) == 1
    assert recorder.calls[0]["worker_name"] == "stub_campaign_worker"
    assert recorder.calls[0]["item_key"] == item_key


@pytest.mark.asyncio
async def test_scheduled_end_completion_generates_report(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = _StubCampaignWorker()
    worker._is_within_sending_hours = MagicMock(return_value=False)  # type: ignore[method-assign]
    campaign_id = uuid4()
    campaign = SimpleNamespace(
        id=campaign_id,
        name="Ended campaign",
        scheduled_end=datetime.now(UTC) - timedelta(minutes=1),
        sending_hours_start=None,
        sending_hours_end=None,
        sending_days=None,
        timezone="UTC",
        status=CampaignStatus.RUNNING,
        completed_at=None,
    )
    db = AsyncMock()
    service = MagicMock()
    service.generate_report = AsyncMock()
    service_class = MagicMock(return_value=service)
    monkeypatch.setattr(base_campaign_worker_module, "CampaignReportService", service_class)

    await worker._process_campaign(campaign, db)

    assert campaign.status == CampaignStatus.COMPLETED
    assert campaign.completed_at is not None
    service.generate_report.assert_awaited_once_with(db, campaign_id)
    worker._is_within_sending_hours.assert_not_called()
    db.commit.assert_awaited_once()


# --- RF-006: shared sending-day decisions for SMS and voice ------------------

MON_FRI = [0, 1, 2, 3, 4]  # Monday=0 contract (app.core.sending_days)
WEEK_OF_MONDAY = date(2026, 10, 5)


def _schedule(days: list[int] | None, tz: str = "America/New_York") -> SimpleNamespace:
    return SimpleNamespace(
        sending_days=days,
        sending_hours_start=time(0, 0),
        sending_hours_end=time(23, 59),
        timezone=tz,
    )


SMS_AND_VOICE = [
    pytest.param(_StubCampaignWorker, id="sms"),
    pytest.param(VoiceCampaignWorker, id="voice"),
]


@pytest.mark.parametrize("worker_cls", SMS_AND_VOICE)
@pytest.mark.parametrize("offset", range(7))
def test_every_weekday_respects_monday_to_friday(worker_cls: type, offset: int) -> None:
    local_noon = datetime.combine(
        WEEK_OF_MONDAY + timedelta(days=offset), time(12), tzinfo=ZoneInfo("America/New_York")
    )
    allowed = worker_cls()._is_within_sending_hours(_schedule(MON_FRI), now=local_noon)
    assert allowed is (local_noon.strftime("%A") not in {"Saturday", "Sunday"})


@pytest.mark.parametrize("worker_cls", SMS_AND_VOICE)
@pytest.mark.parametrize(
    ("tz", "utc_instant", "local_day", "allowed"),
    [
        # UTC is already Saturday, but it is still Friday evening in New York.
        ("America/New_York", datetime(2026, 10, 10, 2, tzinfo=UTC), "Friday", True),
        # UTC is Monday, but it is still Sunday night in New York.
        ("America/New_York", datetime(2026, 10, 12, 3, tzinfo=UTC), "Sunday", False),
        # UTC is Sunday, but Tokyo has already reached Monday.
        ("Asia/Tokyo", datetime(2026, 10, 11, 16, tzinfo=UTC), "Monday", True),
        # UTC is Friday, but Tokyo has already reached Saturday.
        ("Asia/Tokyo", datetime(2026, 10, 9, 16, tzinfo=UTC), "Saturday", False),
    ],
)
def test_sending_day_uses_campaign_local_date(
    worker_cls: type, tz: str, utc_instant: datetime, local_day: str, allowed: bool
) -> None:
    assert utc_instant.astimezone(ZoneInfo(tz)).strftime("%A") == local_day
    assert worker_cls()._is_within_sending_hours(_schedule(MON_FRI, tz), now=utc_instant) is allowed


@pytest.mark.parametrize("worker_cls", SMS_AND_VOICE)
def test_frontend_selected_monday_to_friday_matches_worker(worker_cls: type) -> None:
    # The dashboard picker labels Mon..Fri as 0..4 (frontend/src/lib/constants.ts).
    picker = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
    selected = [picker[label] for label in ("Mon", "Tue", "Wed", "Thu", "Fri")]
    saved = CampaignCreate(
        name="x", from_phone_number="+15550000000", initial_message="hi", sending_days=selected
    ).sending_days
    worker = worker_cls()
    tz = ZoneInfo("America/New_York")
    allowed = {
        day.strftime("%a")
        for day in (WEEK_OF_MONDAY + timedelta(days=i) for i in range(7))
        if worker._is_within_sending_hours(
            _schedule(saved), now=datetime.combine(day, time(12), tzinfo=tz)
        )
    }
    assert allowed == {"Mon", "Tue", "Wed", "Thu", "Fri"}


@pytest.mark.parametrize("worker_cls", SMS_AND_VOICE)
@pytest.mark.parametrize(
    ("days", "allowed_day"), [([5, 6], "Saturday"), ([6], "Sunday"), (None, "Sunday")]
)
def test_weekend_single_day_and_legacy_schedules(
    worker_cls: type, days: list[int] | None, allowed_day: str
) -> None:
    tz = ZoneInfo("America/New_York")
    day = WEEK_OF_MONDAY + timedelta(days=5 if allowed_day == "Saturday" else 6)
    now = datetime.combine(day, time(12), tzinfo=tz)
    assert worker_cls()._is_within_sending_hours(_schedule(days), now=now) is True
    weekday_noon = datetime.combine(WEEK_OF_MONDAY, time(12), tzinfo=tz)
    assert worker_cls()._is_within_sending_hours(_schedule(days), now=weekday_noon) is (
        days is None
    )


@pytest.mark.parametrize("worker_cls", SMS_AND_VOICE)
def test_quiet_hours_still_apply_on_a_sending_day(worker_cls: type) -> None:
    campaign = _schedule(MON_FRI)
    campaign.sending_hours_start, campaign.sending_hours_end = time(9), time(17)
    monday_late = datetime.combine(WEEK_OF_MONDAY, time(20), tzinfo=ZoneInfo("America/New_York"))
    assert worker_cls()._is_within_sending_hours(campaign, now=monday_late) is False


def test_voice_retry_slot_skips_weekend_for_monday_to_friday() -> None:
    tz = ZoneInfo("America/New_York")
    friday_evening = datetime.combine(date(2026, 10, 9), time(18), tzinfo=tz)
    campaign = _schedule(MON_FRI)
    campaign.sending_hours_start, campaign.sending_hours_end = time(9), time(17)
    slot = next_local_slot(campaign, friday_evening.astimezone(UTC)).astimezone(tz)
    assert slot.strftime("%A") == "Monday"
