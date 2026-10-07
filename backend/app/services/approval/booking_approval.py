"""Execute operator-approved ``book_appointment`` actions.

The AI proposes a slot; an operator approves it; this handler books it later,
outside the conversation that produced it. Everything the booking needs is
re-resolved from trusted state rather than the model-supplied payload:

* Cal.com credentials — the action's own workspace connection
  (``resolve_calcom_credentials``); a payload ``api_key`` is never read.
* Agent, event type and staff — the action's agent, scoped to its workspace.
* Contact — the conversation/call recorded in the server-built ``context``.
* Timezone — the workspace setting.

Only the requested date/time, attendee email (fallback: the contact's email),
duration, notes and skill come from the payload, and each is validated.

Outcomes are honest: ``booked`` only after Cal.com returns a booking uid *and*
the Appointment row is flushed. Failures carry ``error_code`` and ``retryable``
so the operator can fix configuration or pick another slot and retry.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pending_action import PendingAction

logger = structlog.get_logger(__name__)

BOOKING_CONTACT_MISSING = "booking_contact_missing"
BOOKING_ATTENDEE_EMAIL_MISSING = "booking_attendee_email_missing"
BOOKING_INVALID_SLOT = "booking_invalid_slot"
BOOKING_SLOT_IN_PAST = "booking_slot_in_past"
BOOKING_PERSIST_FAILED = "booking_persist_failed"

# Failures that a retry cannot fix, or where a retry could double-book.
NON_RETRYABLE_BOOKING_CODES = frozenset(
    {
        BOOKING_CONTACT_MISSING,
        BOOKING_INVALID_SLOT,
        BOOKING_PERSIST_FAILED,
        "booking_not_confirmed",
    }
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MIN_DURATION = 5
_MAX_DURATION = 480
_MAX_NOTES = 2000


def parse_slot(date_str: str, time_str: str, timezone: str) -> datetime | None:
    """Return the aware local datetime for a YYYY-MM-DD / HH:MM slot, or None."""
    if not _DATE_RE.match(date_str or "") or not _TIME_RE.match(time_str or ""):
        return None
    try:
        tz = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")
    try:
        return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    except ValueError:
        return None


def _parse_provider_start(start_iso: str | None, fallback: datetime) -> datetime:
    if not start_iso:
        return fallback
    try:
        parsed = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    except ValueError:
        return fallback
    return parsed if parsed.tzinfo else fallback


def _failed(
    code: str,
    message: str,
    *,
    requested_slot: dict[str, str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "failed",
        "error": message,
        "error_code": code,
        "retryable": code not in NON_RETRYABLE_BOOKING_CODES,
    }
    if requested_slot:
        result["requested_slot"] = requested_slot
    result.update(extra)
    return result


async def _resolve_contact_id(db: AsyncSession, action: PendingAction) -> int | None:
    """Find the contact from server-built queue context, scoped to the workspace."""
    from app.models.conversation import Conversation, Message

    context = action.context or {}
    raw_contact_id = context.get("contact_id")
    if raw_contact_id is not None:
        try:
            return int(raw_contact_id)
        except (TypeError, ValueError):
            return None

    conversation_id = context.get("conversation_id")
    if conversation_id:
        try:
            conversation_uuid = uuid.UUID(str(conversation_id))
        except ValueError:
            return None
        result = await db.execute(
            select(Conversation.contact_id).where(
                Conversation.id == conversation_uuid,
                Conversation.workspace_id == action.workspace_id,
            )
        )
        return result.scalar_one_or_none()

    call_id = context.get("call_id")
    if call_id:
        result = await db.execute(
            select(Conversation.contact_id)
            .join(Message, Message.conversation_id == Conversation.id)
            .where(
                Message.provider_message_id == str(call_id),
                Conversation.workspace_id == action.workspace_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()
    return None


@dataclass(slots=True, frozen=True)
class BookAppointmentActionHandler:
    """Book an approved AI appointment request through BookingService."""

    action_type: str = "book_appointment"

    async def execute(self, db: AsyncSession, action: PendingAction) -> dict[str, Any]:  # noqa: PLR0911, PLR0912, PLR0915
        from app.models.agent import Agent
        from app.models.appointment import Appointment, AppointmentStatus
        from app.models.contact import Contact
        from app.services.ai.message_context_builder import get_workspace_timezone
        from app.services.calendar.booking import BOOKING_SLOT_UNAVAILABLE, BookingService
        from app.services.calendar.calcom_credentials import (
            CALCOM_EVENT_TYPE_MISSING,
            CalComCredentialError,
            resolve_calcom_credentials,
        )
        from app.services.calendar.staff_assignment import resolve_staff_for_booking

        log = logger.bind(pending_action_id=str(action.id), workspace_id=str(action.workspace_id))
        payload = action.action_payload or {}
        date_str = str(payload.get("date") or "")
        time_str = str(payload.get("time") or "")
        requested_slot = {"date": date_str, "time": time_str}

        try:
            credentials = await resolve_calcom_credentials(db, action.workspace_id)
        except CalComCredentialError as exc:
            log.warning("approved_booking_unconfigured", error_code=exc.code)
            return _failed(exc.code, exc.message, requested_slot=requested_slot)

        agent: Agent | None = None
        if action.agent_id is not None:
            agent_result = await db.execute(
                select(Agent).where(
                    Agent.id == action.agent_id,
                    Agent.workspace_id == action.workspace_id,
                )
            )
            agent = agent_result.scalar_one_or_none()

        contact_id = await _resolve_contact_id(db, action)
        contact: Contact | None = None
        if contact_id is not None:
            contact_result = await db.execute(
                select(Contact).where(
                    Contact.id == contact_id,
                    Contact.workspace_id == action.workspace_id,
                )
            )
            contact = contact_result.scalar_one_or_none()
        if contact is None:
            return _failed(
                BOOKING_CONTACT_MISSING,
                "The contact for this booking request could not be found in this workspace.",
                requested_slot=requested_slot,
            )

        email = str(payload.get("email") or contact.email or "").strip()
        if not _EMAIL_RE.match(email):
            return _failed(
                BOOKING_ATTENDEE_EMAIL_MISSING,
                "A valid attendee email is required. Add an email to the contact, then retry.",
                requested_slot=requested_slot,
            )
        attendee_name = (contact.full_name or "").strip() or str(payload.get("name") or "").strip()
        attendee_name = attendee_name[:200] or "Customer"

        timezone = await get_workspace_timezone(action.workspace_id, db)
        local_start = parse_slot(date_str, time_str, timezone)
        if local_start is None:
            return _failed(
                BOOKING_INVALID_SLOT,
                "The requested date/time is not valid (expected YYYY-MM-DD and HH:MM).",
                requested_slot=requested_slot,
            )
        if local_start <= datetime.now(UTC):
            return _failed(
                BOOKING_SLOT_IN_PAST,
                "The requested time has already passed. Retry with a new time.",
                requested_slot=requested_slot,
            )

        try:
            duration = int(payload.get("duration_minutes") or 30)
        except (TypeError, ValueError):
            duration = 30
        duration = max(_MIN_DURATION, min(duration, _MAX_DURATION))
        notes = payload.get("notes")
        notes = str(notes)[:_MAX_NOTES] if notes else None

        # Idempotency: a scheduled, provider-confirmed appointment for this
        # contact and instant means an earlier attempt (or the Cal.com webhook)
        # already booked it. Report that booking instead of creating another.
        existing_result = await db.execute(
            select(Appointment).where(
                Appointment.workspace_id == action.workspace_id,
                Appointment.contact_id == contact.id,
                Appointment.scheduled_at == local_start,
                Appointment.status == AppointmentStatus.SCHEDULED,
                Appointment.calcom_booking_uid.is_not(None),
            )
        )
        existing = existing_result.scalars().first()
        if existing is not None:
            log.info("approved_booking_already_exists", appointment_id=existing.id)
            return {
                "status": "booked",
                "deduplicated": True,
                "appointment_id": existing.id,
                "booking_uid": existing.calcom_booking_uid,
                "booking_id": existing.calcom_booking_id,
                "event_type_id": existing.calcom_event_type_id,
                "scheduled_at": existing.scheduled_at.isoformat(),
                "timezone": timezone,
            }

        event_type_id: int | None = agent.calcom_event_type_id if agent else None
        staff_id: uuid.UUID | None = None
        if agent is not None:
            staff = await resolve_staff_for_booking(
                db,
                agent=agent,
                required_skill=payload.get("skill"),
                commit=False,
            )
            if staff and staff.calcom_event_type_id:
                event_type_id = staff.calcom_event_type_id
                staff_id = staff.id
        if not event_type_id:
            return _failed(
                CALCOM_EVENT_TYPE_MISSING,
                "No Cal.com event type is configured for this agent. "
                "Set the agent's Cal.com event type in agent settings, then retry.",
                requested_slot=requested_slot,
            )

        service = BookingService(
            api_key=credentials.api_key,
            event_type_id=event_type_id,
            timezone=timezone,
        )
        try:
            booking = await service.book_appointment(
                date_str=date_str,
                time_str=time_str,
                email=email,
                contact_name=attendee_name,
                duration_minutes=duration,
                metadata={"source": "approval", "pending_action_id": str(action.id)},
                phone_number=contact.phone_number,
                # The slot may have been taken between proposal and approval.
                pre_validate=True,
            )
        finally:
            await service.close()

        if not booking.success:
            code = booking.error_code or "calcom_provider_error"
            log.warning("approved_booking_failed", error_code=code)
            extra: dict[str, Any] = {}
            if code == BOOKING_SLOT_UNAVAILABLE:
                extra["alternative_slots"] = [
                    {"date": slot.date, "time": slot.time}
                    for slot in booking.alternative_slots
                    if slot.date and slot.time
                ]
            return _failed(
                code,
                booking.error or "Booking failed",
                requested_slot=requested_slot,
                **extra,
            )

        scheduled_at = _parse_provider_start(booking.start_iso, local_start)
        appointment = Appointment(
            workspace_id=action.workspace_id,
            contact_id=contact.id,
            agent_id=agent.id if agent else None,
            bookable_staff_id=staff_id,
            scheduled_at=scheduled_at,
            duration_minutes=duration,
            status=AppointmentStatus.SCHEDULED,
            notes=notes,
            calcom_booking_uid=booking.booking_uid,
            calcom_booking_id=booking.booking_id,
            calcom_event_type_id=event_type_id,
            sync_status="synced",
            last_synced_at=datetime.now(UTC),
        )
        try:
            # A savepoint keeps the action-row claim lock if the insert fails.
            async with db.begin_nested():
                db.add(appointment)
                await db.flush()
        except Exception:
            # The provider booked the slot but the local row did not save.
            # Never retry automatically: that would book the slot twice.
            log.exception("approved_booking_persist_failed", booking_uid=booking.booking_uid)
            return _failed(
                BOOKING_PERSIST_FAILED,
                "Cal.com confirmed the booking but saving the appointment failed. "
                "Check the calendar before booking again.",
                requested_slot=requested_slot,
                booking_uid=booking.booking_uid,
            )

        log.info("approved_booking_created", appointment_id=appointment.id)
        result: dict[str, Any] = {
            "status": "booked",
            "appointment_id": appointment.id,
            "booking_uid": booking.booking_uid,
            "booking_id": booking.booking_id,
            "event_type_id": event_type_id,
            "scheduled_at": scheduled_at.isoformat(),
            "timezone": timezone,
        }
        if staff_id:
            result["assigned_staff_id"] = str(staff_id)
        return result
