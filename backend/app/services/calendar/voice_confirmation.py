"""Persist explicit spoken reconfirmation for the matching outbound call only."""

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.appointment import Appointment, AppointmentStatus
from app.models.conversation import Conversation, Message, MessageStatus
from app.services.idempotency import derive_outbound_key

# An ambiguous paraphrase or a voicemail must not become forensic proof.
_AFFIRMATIVE = re.compile(
    r"^(?:yes|yeah|yep|sure|absolutely|confirmed|i confirm|i(?:'ll| will) be there|"
    r"i(?:'ll| will) attend|see you there)(?:[,\s.!]+(?:i(?:'ll| will) be there))?[.!]*$",
    re.IGNORECASE,
)


async def confirm_from_voice(
    db: AsyncSession,
    *,
    call_control_id: str,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    caller_quote: str,
) -> bool:
    """Accept only an explicit yes on an answered, matching reconfirm call."""
    if not isinstance(caller_quote, str) or not _AFFIRMATIVE.fullmatch(caller_quote.strip()):
        return False
    message = await db.scalar(
        select(Message)
        .join(Conversation)
        .options(selectinload(Message.conversation))
        .where(
            Message.provider_message_id == call_control_id,
            Message.agent_id == agent_id,
            Message.direction == "outbound",
            Message.status == MessageStatus.ANSWERED,
            Conversation.workspace_id == workspace_id,
        )
    )
    if message is None or not message.body.startswith("appointment_reconfirm:"):
        return False
    try:
        appointment_id = int(message.body.partition(":")[2])
    except ValueError:
        return False
    appointment = await db.scalar(
        select(Appointment)
        .where(
            Appointment.id == appointment_id,
            Appointment.workspace_id == workspace_id,
            Appointment.contact_id == message.conversation.contact_id,
            Appointment.agent_id == agent_id,
            Appointment.status == AppointmentStatus.SCHEDULED,
            Appointment.scheduled_at > datetime.now(UTC),
        )
        .with_for_update()
    )
    if appointment is None or message.idempotency_key != derive_outbound_key(
        "appointment_reconfirm_call", appointment.id, appointment.scheduled_at
    ):
        return False
    if appointment.confirmed_at is None:
        appointment.confirmed_at = datetime.now(UTC)
        await db.commit()
    return True
