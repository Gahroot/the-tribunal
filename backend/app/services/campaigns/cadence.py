"""Bounded voice/SMS cadence for voice campaigns.

Six voice attempts across fourteen days at most; SMS fallback is a single,
consent-checked touch after a failed call. All timestamps are stored in UTC.
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


def next_local_slot(
    campaign: Campaign, earliest: datetime, *, hour: int | None = None
) -> datetime:
    """Find the first permitted local slot after earliest, including DST boundaries."""
    tz = ZoneInfo(campaign.timezone or "UTC")
    local = earliest.astimezone(tz)
    start = campaign.sending_hours_start or time(9)
    end = campaign.sending_hours_end or time(17)
    # Prefer observed hour, otherwise morning and late-afternoon contact peaks.
    hours = [hour] if hour is not None and start <= time(hour) <= end else [10, 16]
    for day_offset in range(16):
        day = local.date() + timedelta(days=day_offset)
        if campaign.sending_days and day.weekday() not in campaign.sending_days:
            continue
        for candidate_hour in hours:
            candidate_time = time(candidate_hour)
            if not start <= candidate_time <= end:
                continue
            candidate = datetime.combine(day, candidate_time, tzinfo=tz)
            if (
                candidate.astimezone(UTC) >= earliest
                and candidate.astimezone(tz).hour == candidate_hour
            ):
                return candidate.astimezone(UTC)
    # No legal slot (e.g. configured hours exclude both peaks). Use earliest;
    # the worker still enforces the campaign's sending window before dialing.
    return earliest


def route_call_outcome(
    campaign: Campaign,
    contact: CampaignContact,
    outcome: str,
    now: datetime,
    *, best_hour: int | None = None,
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
