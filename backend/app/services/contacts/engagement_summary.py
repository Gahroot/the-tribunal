"""Contact engagement summary service.

Provides aggregated engagement counts for a single contact across
messages, calls, and appointments — without loading full rows.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.call_outcome import CallOutcome
from app.models.conversation import Conversation, Message
from app.schemas.contact import ContactEngagementSummary
from app.services.contacts.contact_repository import get_contact_by_id
from app.utils.phone import normalize_phone_safe

ANSWERED_OUTCOMES = frozenset(
    {"completed", "appointment_booked", "lead_qualified", "voicemail"}
)


async def get_engagement_summary(
    db: AsyncSession,
    contact_id: int,
    workspace_id: uuid.UUID,
) -> ContactEngagementSummary:
    """Compute aggregated engagement stats for a contact.

    Uses COUNT queries rather than loading rows.
    """
    contact = await get_contact_by_id(contact_id, workspace_id, db)
    if not contact:
        return ContactEngagementSummary(
            total_messages_sent=0,
            total_messages_received=0,
            total_calls=0,
            total_calls_answered=0,
            total_appointments=0,
            events_last_7d=0,
            events_last_30d=0,
            last_activity_at=None,
            channels_used=[],
        )

    now = datetime.now(UTC)
    since_7d = now - timedelta(days=7)
    since_30d = now - timedelta(days=30)

    normalized_phone = (
        normalize_phone_safe(contact.phone_number) if contact.phone_number else None
    )

    conv_conditions = [Conversation.contact_id == contact_id]
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

    sent_stmt = msg_base.where(
        Message.direction == "outbound",
        Message.channel != "voice",
    )
    received_stmt = msg_base.where(
        Message.direction == "inbound",
        Message.channel != "voice",
    )
    calls_stmt = msg_base.where(Message.channel == "voice")

    calls_answered_stmt = (
        select(func.count())
        .select_from(Message)
        .join(CallOutcome, CallOutcome.message_id == Message.id)
        .where(
            Message.conversation_id.in_(conv_id_subq),
            Message.channel == "voice",
            CallOutcome.outcome_type.in_(ANSWERED_OUTCOMES),
        )
    )

    appointments_stmt = (
        select(func.count())
        .select_from(Appointment)
        .where(
            Appointment.workspace_id == workspace_id,
            Appointment.contact_id == contact_id,
        )
    )

    events_7d_stmt = msg_base.where(Message.created_at >= since_7d)
    events_30d_stmt = msg_base.where(Message.created_at >= since_30d)

    last_msg_stmt = select(func.max(Message.created_at)).where(
        Message.conversation_id.in_(conv_id_subq)
    )
    last_appt_stmt = select(func.max(Appointment.created_at)).where(
        Appointment.workspace_id == workspace_id,
        Appointment.contact_id == contact_id,
    )

    channels_stmt = (
        select(Message.channel)
        .where(Message.conversation_id.in_(conv_id_subq))
        .distinct()
    )

    total_sent = (await db.scalar(sent_stmt)) or 0
    total_received = (await db.scalar(received_stmt)) or 0
    total_calls = (await db.scalar(calls_stmt)) or 0
    total_calls_answered = (await db.scalar(calls_answered_stmt)) or 0
    total_appointments = (await db.scalar(appointments_stmt)) or 0
    events_7d = (await db.scalar(events_7d_stmt)) or 0
    events_30d = (await db.scalar(events_30d_stmt)) or 0
    last_msg_at = await db.scalar(last_msg_stmt)
    last_appt_at = await db.scalar(last_appt_stmt)

    channel_rows = (await db.execute(channels_stmt)).scalars().all()
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
        total_messages_sent=int(total_sent),
        total_messages_received=int(total_received),
        total_calls=int(total_calls),
        total_calls_answered=int(total_calls_answered),
        total_appointments=int(total_appointments),
        events_last_7d=int(events_7d),
        events_last_30d=int(events_30d),
        last_activity_at=last_activity_at,
        channels_used=channels_used,
    )
