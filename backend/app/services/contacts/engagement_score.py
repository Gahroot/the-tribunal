"""Recency-weighted engagement scoring for contacts."""

from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_outcome import CallOutcome
from app.models.contact import Contact
from app.models.conversation import Conversation, Message

EngagementEvent = Literal[
    "sms_in",
    "sms_out",
    "call_answered",
    "call_completed",
    "email_opened",
    "email_clicked",
    "email_replied",
    "link_clicked",
]

EVENT_WEIGHTS: dict[str, int] = {
    "sms_in": 20,
    "sms_out": 2,
    "call_answered": 15,
    "call_completed": 25,
    "email_opened": 5,
    "email_clicked": 15,
    "email_replied": 25,
    "link_clicked": 15,
}

WINDOW_DAYS = 30


def _recency_factor(event_at: datetime, now: datetime) -> float:
    """Linear decay over 30 days. Returns 0.0-1.0."""
    age_days = (now - event_at).total_seconds() / 86400.0
    if age_days <= 0:
        return 1.0
    if age_days >= WINDOW_DAYS:
        return 0.0
    return 1.0 - (age_days / WINDOW_DAYS)


def _message_weight(message: Message) -> int:
    """Derive an event weight for a historical Message row."""
    if message.channel == "sms":
        if message.direction == "inbound":
            return EVENT_WEIGHTS["sms_in"]
        return EVENT_WEIGHTS["sms_out"]
    if message.channel in ("voice", "voicemail"):
        duration = message.duration_seconds or 0
        if duration <= 0:
            return 0
        if duration >= 30:
            return EVENT_WEIGHTS["call_completed"]
        return EVENT_WEIGHTS["call_answered"]
    return 0


async def record_engagement(
    db: AsyncSession,
    contact_id: int,
    event_type: EngagementEvent,
) -> None:
    """Record an engagement event and recompute the contact's engagement score.

    Updates `last_engaged_at` to now and recomputes `engagement_score` as a
    recency-weighted sum of events in the last 30 days, clamped to 0-100.
    The caller is responsible for committing the surrounding transaction.
    """
    contact = await db.get(Contact, contact_id)
    if contact is None:
        return

    now = datetime.now(UTC)
    cutoff = now - timedelta(days=WINDOW_DAYS)

    # Pull recent Messages for this contact (via its conversations).
    message_rows = await db.execute(
        select(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.contact_id == contact_id,
            Message.created_at >= cutoff,
        )
    )
    messages = list(message_rows.scalars().all())

    # Pull recent CallOutcome rows for calls in this window.
    outcome_rows = await db.execute(
        select(CallOutcome)
        .join(Message, Message.id == CallOutcome.message_id)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.contact_id == contact_id,
            CallOutcome.created_at >= cutoff,
        )
    )
    outcomes = list(outcome_rows.scalars().all())

    score = 0.0
    for message in messages:
        weight = _message_weight(message)
        if weight == 0:
            continue
        # Ensure tz-aware comparison.
        created_at = message.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        score += weight * _recency_factor(created_at, now)

    for outcome in outcomes:
        if outcome.outcome_type in ("completed", "appointment_booked", "lead_qualified"):
            extra = EVENT_WEIGHTS["call_completed"] - EVENT_WEIGHTS["call_answered"]
            created_at = outcome.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            score += extra * _recency_factor(created_at, now)

    # Add the live event on top so it's immediately reflected even if the
    # row hasn't been flushed/committed yet.
    score += EVENT_WEIGHTS[event_type]

    contact.engagement_score = max(0, min(100, int(round(score))))
    contact.last_engaged_at = now
