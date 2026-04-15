"""Recency-weighted engagement scoring for contacts."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.conversation import Conversation, Message

WINDOW_DAYS = 30
WINDOW_SECONDS = WINDOW_DAYS * 86400


async def record_engagement(db: AsyncSession, contact_id: int) -> None:
    """Recompute a contact's engagement score from the last 30 days of activity.

    Updates `last_engaged_at` to now and `engagement_score` to a recency-weighted
    sum of recent messages and calls, clamped to 0-100. Runs as a single
    aggregate query plus one UPDATE — safe to call on every inbound webhook.
    The caller owns the transaction.
    """
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=WINDOW_DAYS)

    weight = case(
        (
            (Message.channel == "sms") & (Message.direction == "inbound"),
            20,
        ),
        (
            (Message.channel == "sms") & (Message.direction == "outbound"),
            2,
        ),
        (
            Message.channel.in_(("voice", "voicemail"))
            & (func.coalesce(Message.duration_seconds, 0) >= 30),
            25,
        ),
        (
            Message.channel.in_(("voice", "voicemail"))
            & (func.coalesce(Message.duration_seconds, 0) > 0),
            15,
        ),
        else_=0,
    )
    age_seconds = func.extract("epoch", now - Message.created_at)
    decay = func.greatest(0.0, 1.0 - age_seconds / float(WINDOW_SECONDS))

    score_stmt = (
        select(func.coalesce(func.sum(weight * decay), 0.0))
        .select_from(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.contact_id == contact_id,
            Message.created_at >= cutoff,
        )
    )
    raw_score = await db.scalar(score_stmt) or 0.0
    score = max(0, min(100, int(round(float(raw_score)))))

    await db.execute(
        update(Contact)
        .where(Contact.id == contact_id)
        .values(engagement_score=score, last_engaged_at=now)
    )
