"""Contact engagement summary service.

Provides aggregated engagement counts for a single contact across
messages, calls, and appointments — without loading full rows.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.call_outcome import CallOutcome
from app.models.contact import Contact
from app.models.conversation import Conversation, Message
from app.schemas.contact import ContactEngagementSummary
from app.utils.phone import normalize_phone_safe

ANSWERED_OUTCOMES = frozenset(
    {"completed", "appointment_booked", "lead_qualified", "voicemail"}
)


async def get_engagement_summary(
    db: AsyncSession,
    contact: Contact,
    workspace_id: uuid.UUID,
) -> ContactEngagementSummary:
    """Compute aggregated engagement stats for a contact."""
    now = datetime.now(UTC)
    since_7d = now - timedelta(days=7)
    since_30d = now - timedelta(days=30)

    normalized_phone = (
        normalize_phone_safe(contact.phone_number) if contact.phone_number else None
    )

    conv_conditions = [Conversation.contact_id == contact.id]
    if contact.phone_number:
        conv_conditions.append(Conversation.contact_phone == contact.phone_number)
    if normalized_phone:
        conv_conditions.append(Conversation.contact_phone == normalized_phone)

    conv_id_subq = (
        select(Conversation.id)
        .where(
            Conversation.workspace_id == workspace_id,
            or_(*conv_conditions),
        )
        .scalar_subquery()
    )

    msg_base = select(func.count()).select_from(Message).where(
        Message.conversation_id.in_(conv_id_subq)
    )

    results = await asyncio.gather(
        db.scalar(
            msg_base.where(Message.direction == "outbound", Message.channel != "voice")
        ),
        db.scalar(
            msg_base.where(Message.direction == "inbound", Message.channel != "voice")
        ),
        db.scalar(msg_base.where(Message.channel == "voice")),
        db.scalar(
            select(func.count())
            .select_from(Message)
            .join(CallOutcome, CallOutcome.message_id == Message.id)
            .where(
                Message.conversation_id.in_(conv_id_subq),
                Message.channel == "voice",
                CallOutcome.outcome_type.in_(ANSWERED_OUTCOMES),
            )
        ),
        db.scalar(
            select(func.count())
            .select_from(Appointment)
            .where(
                Appointment.workspace_id == workspace_id,
                Appointment.contact_id == contact.id,
            )
        ),
        db.scalar(msg_base.where(Message.created_at >= since_7d)),
        db.scalar(msg_base.where(Message.created_at >= since_30d)),
        db.scalar(
            select(func.max(Message.created_at)).where(
                Message.conversation_id.in_(conv_id_subq)
            )
        ),
        db.scalar(
            select(func.max(Appointment.created_at)).where(
                Appointment.workspace_id == workspace_id,
                Appointment.contact_id == contact.id,
            )
        ),
    )
    total_sent = cast(int | None, results[0])
    total_received = cast(int | None, results[1])
    total_calls = cast(int | None, results[2])
    total_calls_answered = cast(int | None, results[3])
    total_appointments = cast(int | None, results[4])
    events_7d = cast(int | None, results[5])
    events_30d = cast(int | None, results[6])
    last_msg_at = cast(datetime | None, results[7])
    last_appt_at = cast(datetime | None, results[8])

    channel_rows = (
        await db.execute(
            select(Message.channel)
            .where(Message.conversation_id.in_(conv_id_subq))
            .distinct()
        )
    ).scalars().all()
    raw_channels = {c for c in channel_rows if c}
    channels_used: list[str] = []
    if "sms" in raw_channels:
        channels_used.append("sms")
    if raw_channels & {"voice", "voicemail"}:
        channels_used.append("voice")
    if "email" in raw_channels:
        channels_used.append("email")

    last_activity_at: datetime | None = None
    for candidate in (last_msg_at, last_appt_at):
        if candidate is None:
            continue
        if last_activity_at is None or candidate > last_activity_at:
            last_activity_at = candidate

    return ContactEngagementSummary(
        total_messages_sent=int(total_sent or 0),
        total_messages_received=int(total_received or 0),
        total_calls=int(total_calls or 0),
        total_calls_answered=int(total_calls_answered or 0),
        total_appointments=int(total_appointments or 0),
        events_last_7d=int(events_7d or 0),
        events_last_30d=int(events_30d or 0),
        last_activity_at=last_activity_at,
        channels_used=channels_used,
    )
