"""Bounded voice/SMS cadence for voice campaigns.

Six voice attempts across roughly fourteen days, interleaved with at most
three consent-checked SMS touches. All timestamps are stored in UTC.
"""

import re
from datetime import UTC, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignContact, CampaignContactStatus
from app.models.contact import Contact
from app.models.pending_action import PendingAction


async def approved_best_hour(db: AsyncSession, workspace_id: UUID) -> int | None:
    """Use the latest human-approved best_time suggestion, never a pending proposal."""
    result = await db.execute(
        select(PendingAction.action_payload)
        .where(
            PendingAction.workspace_id == workspace_id,
            PendingAction.action_type == "outbound_improvement.follow_up_campaign",
            PendingAction.status.in_(("approved", "executed")),
        )
        .order_by(PendingAction.reviewed_at.desc())
        .limit(1)
    )
    payload = result.scalar_one_or_none()
    if not isinstance(payload, dict):
        return None
    envelope = payload.get("evidence")
    timing = envelope.get("best_timing") if isinstance(envelope, dict) else None
    if not isinstance(timing, dict):
        return None
    evidence = timing.get("evidence")
    label = evidence.get("best_time") if isinstance(evidence, dict) else None
    if not isinstance(label, str):
        label = timing.get("timing")
    return recommended_hour(label if isinstance(label, str) else None)


def contact_best_hour(
    campaign: Campaign, contact: Contact | None, fallback: int | None
) -> int | None:
    """Prefer the contact's own observed engagement hour to workspace guidance."""
    if contact and contact.last_engaged_at:
        hour = contact.last_engaged_at.astimezone(ZoneInfo(campaign.timezone or "UTC")).hour
        if 9 <= hour <= 17:
            return hour
    return fallback


MAX_CALL_ATTEMPTS = 6
SMS_TOUCH_ATTEMPTS = frozenset({1, 3, 5})
# Relative to the first call. A busy signal gets an earlier alternate-hour slot.
ATTEMPT_DAYS = (0, 0, 2, 4, 7, 14)
NO_CONNECT_SUNSET = 6


def recommended_hour(label: str | None) -> int | None:
    """Only accept an explicit hour in the approved timing recommendation."""
    if not label:
        return None
    match = re.search(
        r"\b(0?[1-9]|1[0-9]|2[0-3])(?::[0-5][0-9])?"
        r"(?:\s*[-–]\s*(?:0?[1-9]|1[0-9]|2[0-3]))?\s*(am|pm)?\b",
        label.lower(),
    )
    if not match:
        return None
    hour = int(match.group(1))
    meridiem = match.group(2)
    if meridiem:
        hour = hour % 12 + (12 if meridiem == "pm" else 0)
    return hour if 9 <= hour <= 17 else None


def next_local_slot(campaign: Campaign, earliest: datetime, *, hour: int | None = None) -> datetime:
    """Find the first permitted local slot after earliest, including DST boundaries."""
    tz = ZoneInfo(campaign.timezone or "UTC")
    local = earliest.astimezone(tz)
    start = campaign.sending_hours_start or time(9)
    end = campaign.sending_hours_end or time(17)
    # Prefer observed hour, otherwise morning and late-afternoon contact peaks.
    # If neither peak fits a configured window, use its first permitted hour.
    hours = (
        [time(hour)] if hour is not None and start <= time(hour) <= end else [time(10), time(16)]
    )
    if not any(start <= value <= end for value in hours):
        hours = [start]
    for day_offset in range(16):
        day = local.date() + timedelta(days=day_offset)
        if campaign.sending_days and day.weekday() not in campaign.sending_days:
            continue
        for candidate_time in hours:
            if not start <= candidate_time <= end:
                continue
            candidate = datetime.combine(day, candidate_time, tzinfo=tz)
            utc_candidate = candidate.astimezone(UTC)
            if utc_candidate >= earliest and utc_candidate.astimezone(tz).replace(
                tzinfo=None
            ) == candidate.replace(tzinfo=None):
                return candidate.astimezone(UTC)
    # A valid weekly sending window always has a slot within sixteen days.
    # Fail closed for invalid windows instead of scheduling outside one.
    raise ValueError("No permitted campaign sending slot within sixteen days")


def sms_touch_pending(campaign: Campaign, contact: CampaignContact) -> bool:
    """Only send between active voice attempts, never after a reply or sunset."""
    return bool(
        campaign.sms_fallback_enabled
        and (
            campaign.sms_fallback_template
            or (campaign.sms_fallback_use_ai and campaign.sms_fallback_agent_id)
        )
        and contact.status
        in {
            CampaignContactStatus.PENDING,
            CampaignContactStatus.SMS_FALLBACK_SENT,
        }
        and not contact.opted_out
        and contact.call_attempts in SMS_TOUCH_ATTEMPTS
        and contact.last_call_status in {"no_answer", "busy", "voicemail"}
        and contact.last_call_at
        and (not contact.last_reply_at or contact.last_reply_at < contact.last_call_at)
        and (
            not contact.sms_fallback_sent_at or contact.sms_fallback_sent_at < contact.last_call_at
        )
        and (contact.messages_sent or 0)
        < (
            campaign.max_messages_per_contact
            if campaign.max_messages_per_contact is not None
            else 5
        )
        and (
            campaign.max_messages_per_campaign is None
            or (campaign.messages_sent or 0) < campaign.max_messages_per_campaign
        )
    )


def sms_touch_due_at(campaign: Campaign, contact: CampaignContact) -> datetime:
    """Earliest legal local SMS slot, at least two hours after a failed call.

    Unlike voice, SMS does not wait for the morning/afternoon call peaks: that
    would crowd the same-day alternate-hour voice attempt.
    """
    assert contact.last_call_at is not None
    earliest = contact.last_call_at + timedelta(hours=2)
    tz = ZoneInfo(campaign.timezone or "UTC")
    local = earliest.astimezone(tz)
    start = campaign.sending_hours_start or time(9)
    end = campaign.sending_hours_end or time(17)
    for day_offset in range(16):
        day = local.date() + timedelta(days=day_offset)
        if campaign.sending_days and day.weekday() not in campaign.sending_days:
            continue
        if day_offset == 0 and start <= local.time() <= end:
            return earliest
        candidate = datetime.combine(day, start, tzinfo=tz)
        utc_candidate = candidate.astimezone(UTC)
        if (
            utc_candidate >= earliest
            and start <= candidate.time() <= end
            and utc_candidate.astimezone(tz).replace(tzinfo=None) == candidate.replace(tzinfo=None)
        ):
            return utc_candidate
    raise ValueError("No permitted SMS sending slot within sixteen days")


def route_call_outcome(
    campaign: Campaign,
    contact: CampaignContact,
    outcome: str,
    now: datetime,
    *,
    best_hour: int | None = None,
) -> None:
    """Advance one completed attempt, never retrying a human or bad number."""
    if outcome in {"answered", "live_human"}:
        contact.status = CampaignContactStatus.CALL_ANSWERED
        contact.next_follow_up_at = None
        return
    if outcome in {"bad_number", "invalid_number", "rejected"}:
        contact.status = CampaignContactStatus.FAILED
        contact.next_follow_up_at = None
        return
    if contact.call_attempts >= min(MAX_CALL_ATTEMPTS, NO_CONNECT_SUNSET):
        contact.status = CampaignContactStatus.COMPLETED
        contact.next_follow_up_at = None
        return

    first = contact.first_sent_at or contact.last_call_at or now
    hour: int | None
    # Escalate busy at an alternate hour; voicemail gives the recipient more time.
    if outcome == "busy" and contact.call_attempts == 1:
        earliest = now + timedelta(hours=4)
        hour = 16 if first.astimezone(ZoneInfo(campaign.timezone or "UTC")).hour < 12 else 10
    elif outcome == "voicemail":
        earliest = max(
            now + timedelta(days=2),
            first + timedelta(days=ATTEMPT_DAYS[min(contact.call_attempts, 5)]),
        )
        hour = best_hour
    else:
        offset = ATTEMPT_DAYS[min(contact.call_attempts, MAX_CALL_ATTEMPTS - 1)]
        if offset == 0:
            earliest = now + timedelta(hours=4)
            hour = 16 if first.astimezone(ZoneInfo(campaign.timezone or "UTC")).hour < 12 else 10
        else:
            earliest = max(now + timedelta(hours=4), first + timedelta(days=offset))
            hour = best_hour
    contact.next_follow_up_at = next_local_slot(campaign, earliest, hour=hour)
    contact.status = CampaignContactStatus.PENDING
