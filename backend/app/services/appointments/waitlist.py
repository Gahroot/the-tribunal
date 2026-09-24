"""Offer a new booking opening to an explicitly tagged waitlist contact.

A MEETING_ENDED webhook arrives after the missed time: never advertise that
expired slot as available. The booking page supplies the next real opening.
"""

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.webhooks.calcom_events import send_lifecycle_sms
from app.core.config import settings
from app.models.agent import Agent
from app.models.appointment import Appointment
from app.models.contact import Contact
from app.models.tag import ContactTag, Tag
from app.services.calendar.calcom import CalComService
from app.services.rate_limiting.opt_out_manager import OptOutManager


async def offer_waitlist_opening(db: AsyncSession, appointment: Appointment) -> None:
    """Offer a booking link to one eligible, opted-in waitlist contact."""
    if not appointment.calcom_event_type_id or not settings.calcom_api_key:
        return
    waiting = exists(
        select(ContactTag.id)
        .join(Tag, Tag.id == ContactTag.tag_id)
        .where(
            ContactTag.contact_id == Contact.id,
            Tag.workspace_id == appointment.workspace_id,
            Tag.name == "appointment-waitlist",
        )
    )
    has_booking = exists(
        select(Appointment.id).where(
            Appointment.workspace_id == appointment.workspace_id,
            Appointment.contact_id == Contact.id,
            Appointment.status == "scheduled",
        )
    )
    candidates = (
        await db.scalars(
            select(Contact)
            .where(
                Contact.workspace_id == appointment.workspace_id,
                Contact.id != appointment.contact_id,
                Contact.phone_number.is_not(None),
                waiting,
                ~has_booking,
            )
            .order_by(Contact.created_at, Contact.id)
            .limit(20)
        )
    ).all()
    opt_out = OptOutManager()
    candidate = None
    for waiting_contact in candidates:
        if not await opt_out.check_opt_out(
            appointment.workspace_id, waiting_contact.phone_number, db
        ):
            candidate = waiting_contact
            break
    if candidate is None:
        return
    agent = (
        await db.scalar(
            select(Agent).where(
                Agent.id == appointment.agent_id, Agent.workspace_id == appointment.workspace_id
            )
        )
        if appointment.agent_id
        else None
    )
    url = CalComService(settings.calcom_api_key).generate_booking_url(
        event_type_id=appointment.calcom_event_type_id,
        contact_email=candidate.email or "",
        contact_name=" ".join(filter(None, [candidate.first_name, candidate.last_name])) or "there",
        contact_phone=candidate.phone_number,
    )
    if not url:
        return
    await send_lifecycle_sms(
        db=db,
        workspace_id=appointment.workspace_id,
        contact=candidate,
        agent=agent,
        body_text=(
            f"Hi {candidate.first_name or 'there'}, a booking opportunity is open. "
            f"See available times here: {url}"
        ),
        idempotency_scope="calcom_confirmed_noshow_waitlist",
        idempotency_parts=(appointment.id, candidate.id),
    )
