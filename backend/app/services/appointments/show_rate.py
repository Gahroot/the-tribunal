"""Shared appointment lifecycle side effects for webhook and operator updates."""

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment, AppointmentStatus
from app.models.contact import Contact
from app.models.tag import ContactTag, Tag
from app.services.opportunities.appointment_stages import move_appointment_opportunities
from app.services.tags import TagService


async def record_appointment_outcome(db: AsyncSession, appointment: Appointment) -> None:
    """Record one terminal outcome; call only on an actual state transition."""
    contact = (
        await db.execute(
            select(Contact).where(
                Contact.id == appointment.contact_id,
                Contact.workspace_id == appointment.workspace_id,
            )
        )
    ).scalar_one_or_none()
    if contact is None:
        return
    tags = TagService(db)
    if appointment.status == AppointmentStatus.NO_SHOW:
        cause = "confirmed-then-no-show" if appointment.confirmed_at else "never-confirmed"
        opposite = "never-confirmed" if appointment.confirmed_at else "confirmed-then-no-show"
        await db.execute(
            delete(ContactTag).where(
                ContactTag.contact_id == contact.id,
                ContactTag.tag_id.in_(
                    select(Tag.id).where(
                        Tag.workspace_id == appointment.workspace_id,
                        Tag.name.in_(
                            (
                                f"noshow-{opposite}",
                                "noshow-day3-sent",
                                "noshow-day7-sent",
                                "reengaged-booked",
                            )
                        ),
                    )
                ),
            )
        )
        for name in ("no-show", f"noshow-{cause}", f"noshow-{cause}-{appointment.id}"):
            await tags.add_tag_to_contact(
                workspace_id=appointment.workspace_id, contact_id=contact.id, name=name
            )
        contact.noshow_count = (contact.noshow_count or 0) + 1
        contact.last_appointment_status = "no_show"
    elif appointment.status == AppointmentStatus.COMPLETED:
        await tags.add_tag_to_contact(
            workspace_id=appointment.workspace_id, contact_id=contact.id, name="showed-up"
        )
        contact.last_appointment_status = "completed"
    else:
        return
    # A delayed meeting-ended webhook must not undo a newer booking's stage.
    newer_booking = await db.scalar(
        select(
            exists().where(
                Appointment.workspace_id == appointment.workspace_id,
                Appointment.contact_id == contact.id,
                Appointment.id != appointment.id,
                Appointment.status == AppointmentStatus.SCHEDULED,
                Appointment.scheduled_at > appointment.scheduled_at,
            )
        )
    )
    if newer_booking:
        contact.last_appointment_status = "scheduled"
        return
    await move_appointment_opportunities(
        db, appointment.workspace_id, contact.id, appointment.status
    )
