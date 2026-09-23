"""Cadence routing and contact-local scheduling."""

from datetime import UTC, datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.models.campaign import Campaign, CampaignContact, CampaignContactStatus
from app.models.contact import Contact
from app.services.campaigns.cadence import (
    approved_best_hour,
    contact_best_hour,
    next_local_slot,
    recommended_hour,
    route_call_outcome,
    sms_touch_due_at,
    sms_touch_pending,
)


def campaign() -> Campaign:
    return Campaign(timezone="America/New_York", sending_days=list(range(7)))


def contact(first: datetime, attempts: int = 1) -> CampaignContact:
    return CampaignContact(
        call_attempts=attempts, first_sent_at=first, status=CampaignContactStatus.CALLING
    )


@pytest.mark.asyncio
async def test_approved_best_time_recommendation_is_consumed() -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = {
        "evidence": {"best_timing": {"evidence": {"best_time": "4-5pm"}}}
    }
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    assert await approved_best_hour(db, uuid4()) == 16
    result.scalar_one_or_none.return_value = None
    assert await approved_best_hour(db, uuid4()) is None


def test_no_answer_ladder_and_sunset() -> None:
    first = datetime(2026, 9, 21, 14, tzinfo=UTC)  # 10am New York
    expected_days = [0, 2, 4, 7, 14]
    for attempts, day in enumerate(expected_days, 1):
        cc = contact(first, attempts)
        route_call_outcome(campaign(), cc, "no_answer", first + timedelta(days=max(0, day - 1)))
        assert cc.status == CampaignContactStatus.PENDING
        assert cc.next_follow_up_at is not None
        assert cc.next_follow_up_at >= first + timedelta(days=day)
    cc = contact(first, 6)
    route_call_outcome(campaign(), cc, "no_answer", first + timedelta(days=14))
    assert cc.status == CampaignContactStatus.COMPLETED
    assert cc.next_follow_up_at is None


def test_outcome_paths() -> None:
    first = datetime(2026, 9, 21, 14, tzinfo=UTC)
    busy = contact(first)
    route_call_outcome(campaign(), busy, "busy", first)
    assert busy.next_follow_up_at.astimezone(ZoneInfo("America/New_York")).hour == 16
    voicemail = contact(first)
    route_call_outcome(campaign(), voicemail, "voicemail", first)
    assert voicemail.next_follow_up_at >= first + timedelta(days=2)
    for outcome, status in (
        ("answered", CampaignContactStatus.CALL_ANSWERED),
        ("bad_number", CampaignContactStatus.FAILED),
    ):
        cc = contact(first)
        route_call_outcome(campaign(), cc, outcome, first)
        assert cc.status == status
        assert cc.next_follow_up_at is None


def test_contact_engagement_hour_overrides_approved_workspace_hour() -> None:
    item = Contact(last_engaged_at=datetime(2026, 9, 21, 20, tzinfo=UTC))
    assert contact_best_hour(campaign(), item, 10) == 16
    assert contact_best_hour(campaign(), None, 10) == 10


def test_same_day_sms_preserves_busy_alternate_hour() -> None:
    item = campaign()
    first = datetime(2026, 9, 21, 14, tzinfo=UTC)  # 10am local
    cc = contact(first)
    cc.last_call_at = first
    route_call_outcome(item, cc, "busy", first)
    sms_due = sms_touch_due_at(item, cc)
    assert sms_due.astimezone(ZoneInfo(item.timezone)).hour == 12
    assert cc.next_follow_up_at.astimezone(ZoneInfo(item.timezone)).hour == 16
    assert cc.next_follow_up_at >= sms_due + timedelta(hours=2)


def test_three_paced_sms_touches_across_retry_ladder() -> None:
    item = campaign()
    item.sms_fallback_enabled = True
    item.sms_fallback_template = "Hi {first_name}"
    item.max_messages_per_contact = 5
    item.max_messages_per_campaign = None
    item.messages_sent = 0
    first = datetime(2026, 9, 21, 14, tzinfo=UTC)
    cc = contact(first)
    cc.opted_out = False
    cc.messages_sent = 0
    cc.last_reply_at = None
    cc.sms_fallback_sent_at = None
    for attempt in range(1, 7):
        cc.call_attempts = attempt
        cc.last_call_at = first + timedelta(days=attempt)
        cc.last_call_status = "voicemail"
        cc.status = (
            CampaignContactStatus.PENDING if attempt < 6 else CampaignContactStatus.COMPLETED
        )
        assert sms_touch_pending(item, cc) is (attempt in {1, 3, 5})
        if attempt in {1, 3, 5}:
            due = sms_touch_due_at(item, cc)
            assert due >= cc.last_call_at + timedelta(hours=2)
            cc.sms_fallback_sent_at = due
            assert not sms_touch_pending(item, cc)
    cc.status = CampaignContactStatus.PENDING
    cc.call_attempts = 5
    cc.last_reply_at = cc.last_call_at + timedelta(minutes=1)
    assert not sms_touch_pending(item, cc)
    cc.last_reply_at = None
    cc.opted_out = True
    assert not sms_touch_pending(item, cc)
    cc.opted_out = False
    item.max_messages_per_contact = 0
    assert not sms_touch_pending(item, cc)


def test_local_slot_respects_days_hours_and_dst() -> None:
    item = campaign()
    item.sending_days = [0]
    item.sending_hours_start = time(9)
    item.sending_hours_end = time(17)
    earliest = datetime(2026, 3, 8, 18, tzinfo=UTC)  # Sunday after spring-forward
    result = next_local_slot(item, earliest, hour=16)
    assert result.astimezone(ZoneInfo(item.timezone)).weekday() == 0
    assert result.astimezone(ZoneInfo(item.timezone)).hour == 16
    assert recommended_hour("4pm") == 16
    assert recommended_hour("9-11am") == 9
    assert recommended_hour("4–5pm") == 16
    assert recommended_hour("unknown") is None

    item.sending_hours_start = time(12, 30)
    item.sending_hours_end = time(14)
    result = next_local_slot(item, earliest)
    assert result.astimezone(ZoneInfo(item.timezone)).time() == time(12, 30)
    assert result.astimezone(ZoneInfo(item.timezone)).weekday() == 0
