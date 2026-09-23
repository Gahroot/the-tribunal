"""Handle explicit C/R replies to appointment confirmation invitations."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.agent import Agent
from app.models.appointment import Appointment
from app.models.contact import Contact
from app.models.conversation import Conversation, Message, MessageStatus
from app.services.calendar.calcom import CalComService
from app.services.calendar.reminder_service import resolve_from_number
from app.services.idempotency import derive_outbound_key


async def handle_confirmation_reply(
    db: AsyncSession, message: Message, conversation: Conversation, body: str
) -> bool:
    """Consume a reply only when it matches an outstanding invitation on this thread.

    Never interpret arbitrary SMS as an appointment command: require an exact
    one-letter reply, a scheduled appointment and a previously sent invitation.
    """
    reply = body.strip().upper()
    if reply not in {"C", "R"} or not conversation.contact_id:
        return False

    now = datetime.now(UTC)
    appointments = (
        (
            await db.execute(
                select(Appointment)
                .where(
                    Appointment.workspace_id == conversation.workspace_id,
                    Appointment.contact_id == conversation.contact_id,
                    Appointment.status == "scheduled",
                    Appointment.scheduled_at > now,
                    Appointment.created_at <= message.created_at,
                )
                .order_by(Appointment.scheduled_at)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    invited: list[tuple[datetime, Appointment]] = []
    for appt in appointments:
        if (
            await resolve_from_number(db, appt.contact_id, appt.workspace_id, appt.agent_id)
            != conversation.workspace_phone
        ):
            continue
        # Match the outbound message to this booking, not merely to this phone.
        keys = [
            derive_outbound_key("calcom_booking_confirmation_sms", appt.id),
            derive_outbound_key("calcom_booking_rescheduled_sms", appt.id, appt.scheduled_at),
            *(
                derive_outbound_key("reminder", appt.id, appt.scheduled_at, offset)
                for offset in (appt.reminders_sent or [])
            ),
        ]
        sent_for_appointment = await db.scalar(
            select(Message.created_at)
            .where(
                Message.conversation_id == conversation.id,
                Message.direction == "outbound",
                Message.status != MessageStatus.FAILED,
                Message.body.contains("Reply C to confirm / R to reschedule"),
                Message.idempotency_key.in_(keys),
                Message.created_at >= appt.created_at,
                Message.created_at <= message.created_at,
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        if sent_for_appointment is not None:
            invited.append((sent_for_appointment, appt))
    if invited:
        _, appt = max(invited, key=lambda entry: entry[0])
        if reply == "C" and appt.reschedule_requested_at is None:
            appt.confirmed_at = now
        elif reply == "R" and appt.confirmed_at is None:
            appt.reschedule_requested_at = now
        else:
            return True
        await db.commit()
        from app.api.webhooks.calcom_events import send_lifecycle_sms

        agent = await db.get(Agent, appt.agent_id) if appt.agent_id else None
        contact = await db.get(Contact, appt.contact_id)
        if reply == "C":
            if contact:
                await send_lifecycle_sms(
                    db=db,
                    workspace_id=appt.workspace_id,
                    contact=contact,
                    agent=agent,
                    body_text="Thanks for confirming your appointment. See you then!",
                    idempotency_scope="appointment_confirmation_reply",
                    idempotency_parts=(appt.id, appt.scheduled_at),
                )
            return True
        return await _send_reschedule_link(db, appt, contact, agent)
    return False


async def _send_reschedule_link(
    db: AsyncSession, appt: Appointment, contact: Contact | None, agent: Agent | None
) -> bool:
    """Fall through to the existing AI/operator path if a link cannot be sent."""
    if not (contact and agent and agent.calcom_event_type_id and settings.calcom_api_key):
        return False
    try:
        url = CalComService(settings.calcom_api_key).generate_booking_url(
            event_type_id=agent.calcom_event_type_id,
            contact_email=contact.email or "",
            contact_name=" ".join(filter(None, [contact.first_name, contact.last_name])) or "there",
            contact_phone=contact.phone_number,
        )
    except Exception:
        return False
    from app.api.webhooks.calcom_events import send_lifecycle_sms

    return await send_lifecycle_sms(
        db=db,
        workspace_id=appt.workspace_id,
        contact=contact,
        agent=agent,
        body_text=f"To reschedule your appointment, choose a new time: {url}",
        idempotency_scope="appointment_reschedule_reply",
        idempotency_parts=(appt.id, appt.scheduled_at),
    )
