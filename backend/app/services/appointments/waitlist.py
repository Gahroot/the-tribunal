"""Offer an actual Cal.com opening to a confirmed no-show's opt-in waitlist.

Expired times cannot be reused; offer the next available time in that case.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.webhooks.calcom_events import send_lifecycle_sms
from app.core.config import settings
from app.models.agent import Agent
from app.models.appointment import Appointment, AppointmentStatus
from app.models.contact import Contact
from app.models.tag import ContactTag, Tag
from app.services.calendar.calcom import CalComService
from app.services.rate_limiting.opt_out_manager import OptOutManager


def _future_slots(slots: list[dict[str, Any]], now: datetime) -> list[datetime]:
    """Ignore malformed provider slots; only return bookable future UTC times."""
    available: list[datetime] = []
    for slot in slots:
        value = slot.get("iso") if isinstance(slot, dict) else None
        if not isinstance(value, str):
            continue
        try:
            start = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if start.tzinfo and start > now + timedelta(minutes=15):
            available.append(start.astimezone(UTC))
    return available


async def offer_waitlist_opening(db: AsyncSession, appointment: Appointment) -> None:
    """Release future bookings or offer the next verified time after a missed one."""
    now = datetime.now(UTC)
    if (
        appointment.status != AppointmentStatus.NO_SHOW
        or not appointment.confirmed_at
        or not appointment.calcom_event_type_id
        or not settings.calcom_api_key
    ):
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
    cal = CalComService(settings.calcom_api_key)
    future_slot = appointment.scheduled_at > now + timedelta(minutes=15)
    try:
        if future_slot and (
            not appointment.calcom_booking_uid
            or not await cal.cancel_booking(
                appointment.calcom_booking_uid, reason="Released after operator-marked no-show"
            )
        ):
            return
        slots = await cal.get_availability(
            appointment.calcom_event_type_id,
            appointment.scheduled_at if future_slot else now,
            (appointment.scheduled_at + timedelta(days=1))
            if future_slot
            else now + timedelta(days=7),
            timezone="UTC",
        )
        available = _future_slots(slots, now)
        offered_at = (
            appointment.scheduled_at
            if future_slot and appointment.scheduled_at in available
            else min(available)
            if not future_slot and available
            else None
        )
        if offered_at is None:
            return
        url = cal.generate_booking_url(
            event_type_id=appointment.calcom_event_type_id,
            contact_email=candidate.email or "",
            contact_name=" ".join(filter(None, [candidate.first_name, candidate.last_name]))
            or "there",
            contact_phone=candidate.phone_number,
        )
    finally:
        await cal.close()
    agent = (
        await db.scalar(
            select(Agent).where(
                Agent.id == appointment.agent_id, Agent.workspace_id == appointment.workspace_id
            )
        )
        if appointment.agent_id
        else None
    )
    if not url:
        return
    await send_lifecycle_sms(
        db=db,
        workspace_id=appointment.workspace_id,
        contact=candidate,
        agent=agent,
        body_text=(
            f"Hi {candidate.first_name or 'there'}, "
            f"{offered_at.strftime('%b %d at %I:%M %p UTC')} "
            f"is open for booking (first come, first served). Book here: {url}"
        ),
        idempotency_scope="calcom_confirmed_noshow_waitlist",
        idempotency_parts=(appointment.id, candidate.id),
    )
