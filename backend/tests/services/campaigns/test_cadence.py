"""Cadence routing and contact-local scheduling."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models.campaign import Campaign, CampaignContact, CampaignContactStatus
from app.models.contact import Contact
from app.services.campaigns.cadence import (
    contact_best_hour,
    next_local_slot,
    recommended_hour,
    route_call_outcome,
)


def campaign() -> Campaign:
    return Campaign(timezone="America/New_York", sending_days=list(range(7)))


def contact(first: datetime, attempts: int = 1) -> CampaignContact:
    return CampaignContact(
        call_attempts=attempts, first_sent_at=first, status=CampaignContactStatus.CALLING
    )


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
    for outcome, status in (("answered", CampaignContactStatus.CALL_ANSWERED),
                            ("bad_number", CampaignContactStatus.FAILED)):
        cc = contact(first)
        route_call_outcome(campaign(), cc, outcome, first)
        assert cc.status == status
        assert cc.next_follow_up_at is None


def test_contact_engagement_hour_overrides_approved_workspace_hour() -> None:
    item = Contact(last_engaged_at=datetime(2026, 9, 21, 20, tzinfo=UTC))
    assert contact_best_hour(campaign(), item, 10) == 16
    assert contact_best_hour(campaign(), None, 10) == 10


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
