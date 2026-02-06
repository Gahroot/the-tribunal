"""Cal.com webhook endpoints for appointment events."""

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from fastapi import APIRouter, Request
from sqlalchemy import select

from app.core.webhook_security import verify_calcom_webhook
from app.db.session import AsyncSessionLocal
from app.models.agent import Agent
from app.models.appointment import Appointment, AppointmentStatus
from app.models.contact import Contact
from app.models.conversation import Conversation, Message

router = APIRouter()
logger = structlog.get_logger()


@router.post("/booking")
async def calcom_booking_webhook(request: Request) -> dict[str, str]:
    """Handle Cal.com booking events.

    Cal.com sends webhooks for:
    - booking.created: New booking created
    - booking.rescheduled: Booking rescheduled
    - booking.cancelled: Booking cancelled

    All webhooks are signature-verified before processing.
    """
    log = logger.bind(endpoint="calcom_booking_webhook")

    try:
        await verify_calcom_webhook(request)
    except Exception as e:
        log.error("webhook_verification_failed", error=str(e))
        raise

    try:
        payload = await request.json()
    except Exception as e:
        log.error("invalid_json_payload", error=str(e))
        return {"status": "error", "message": "Invalid JSON"}

    # Extract event data
    trigger = payload.get("trigger", "")
    data = payload.get("data", {})

    log = log.bind(event_type=trigger)
    log.info("webhook_received")

    # Handle different event types
    if trigger == "BOOKING_CREATED":
        await handle_booking_created(data, log)
    elif trigger == "BOOKING_RESCHEDULED":
        await handle_booking_rescheduled(data, log)
    elif trigger == "BOOKING_CANCELLED":
        await handle_booking_cancelled(data, log)
    else:
        log.debug("unhandled_event_type")

    return {"status": "ok"}


async def _find_recent_voice_message(
    db: Any,
    contact_id: int,
    agent_id: Any,
    log: Any,
) -> Any:
    """Find a recent voice message for a contact+agent (within 10 minutes)."""
    import uuid as _uuid

    try:
        cutoff = datetime.now(UTC) - timedelta(minutes=10)
        msg_query = (
            select(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Conversation.contact_id == contact_id,
                Message.channel == "voice",
                Message.created_at >= cutoff,
            )
        )
        if agent_id:
            msg_query = msg_query.where(Message.agent_id == agent_id)
        msg_query = msg_query.order_by(Message.created_at.desc()).limit(1)
        msg_result = await db.execute(msg_query)
        recent_msg = msg_result.scalar_one_or_none()
        if recent_msg:
            msg_id: _uuid.UUID = recent_msg.id
            log.info("linked_appointment_to_message", message_id=str(msg_id))
            return msg_id
    except Exception as e:
        log.warning("message_linking_failed", error=str(e))
    return None


async def handle_booking_created(data: dict[str, Any], log: Any) -> None:
    """Handle new Cal.com booking.

    Args:
        data: Cal.com booking data
        log: Logger instance
    """
    # Extract booking details
    booking_uid = data.get("uid", "")
    booking_id = data.get("id", "")
    event_type_id = data.get("eventTypeId", "")
    scheduled_at_str = data.get("startTime", "")
    duration_minutes = data.get("duration", 30)

    # Extract attendee info
    attendees = data.get("attendees", [])
    if not attendees:
        log.warning("no_attendees_in_booking")
        return

    attendee = attendees[0]
    email = attendee.get("email", "")

    log = log.bind(
        booking_uid=booking_uid,
        booking_id=booking_id,
        email=email,
        event_type_id=event_type_id,
    )
    log.info("processing_booking_created")

    if not all([booking_uid, email, scheduled_at_str]):
        log.warning("missing_required_fields")
        return

    try:
        scheduled_at = datetime.fromisoformat(scheduled_at_str.replace("Z", "+00:00"))
    except Exception as e:
        log.warning("invalid_datetime_format", error=str(e))
        return

    async with AsyncSessionLocal() as db:
        # Look up contact by email
        contact_result = await db.execute(select(Contact).where(Contact.email == email))
        contact = contact_result.scalar_one_or_none()

        if not contact:
            log.warning("contact_not_found", email=email)
            # Create contact if it doesn't exist
            # For now, we skip and just log
            return

        workspace_id = contact.workspace_id

        # Look up agent by event type ID if provided
        agent = None
        if event_type_id:
            agent_result = await db.execute(
                select(Agent).where(
                    Agent.workspace_id == workspace_id,
                    Agent.calcom_event_type_id == int(event_type_id),
                )
            )
            agent = agent_result.scalar_one_or_none()

        # Check if appointment already exists
        existing = await db.execute(
            select(Appointment).where(
                Appointment.calcom_booking_uid == booking_uid,
            )
        )
        appointment = existing.scalar_one_or_none()

        if appointment:
            # Update existing appointment
            log.info("updating_existing_appointment", appointment_id=appointment.id)
            appointment.scheduled_at = scheduled_at
            appointment.duration_minutes = duration_minutes
            appointment.calcom_booking_id = booking_id
            appointment.calcom_event_type_id = int(event_type_id) if event_type_id else None
            appointment.sync_status = "synced"
            appointment.last_synced_at = datetime.now(UTC)
            appointment.sync_error = None  # Clear any previous sync errors
        else:
            message_id = await _find_recent_voice_message(
                db, contact.id, agent.id if agent else None, log,
            )

            # Create new appointment
            appointment = Appointment(
                workspace_id=workspace_id,
                contact_id=contact.id,
                agent_id=agent.id if agent else None,
                message_id=message_id,
                scheduled_at=scheduled_at,
                duration_minutes=duration_minutes,
                status="scheduled",
                calcom_booking_uid=booking_uid,
                calcom_booking_id=booking_id,
                calcom_event_type_id=int(event_type_id) if event_type_id else None,
                sync_status="synced",
                last_synced_at=datetime.now(UTC),
                sync_error=None,
            )
            db.add(appointment)

        await db.commit()
        await db.refresh(appointment)

        log.info(
            "booking_processed",
            appointment_id=appointment.id,
            sync_status="synced",
        )


async def handle_booking_rescheduled(data: dict[str, Any], log: Any) -> None:
    """Handle Cal.com booking reschedule.

    Args:
        data: Cal.com booking data
        log: Logger instance
    """
    booking_uid = data.get("uid", "")
    scheduled_at_str = data.get("startTime", "")
    duration_minutes = data.get("duration", 30)

    log = log.bind(booking_uid=booking_uid)
    log.info("processing_booking_rescheduled")

    if not all([booking_uid, scheduled_at_str]):
        log.warning("missing_required_fields")
        return

    try:
        scheduled_at = datetime.fromisoformat(scheduled_at_str.replace("Z", "+00:00"))
    except Exception as e:
        log.warning("invalid_datetime_format", error=str(e))
        return

    async with AsyncSessionLocal() as db:
        # Find appointment by booking UID
        result = await db.execute(
            select(Appointment).where(
                Appointment.calcom_booking_uid == booking_uid,
            )
        )
        appointment = result.scalar_one_or_none()

        if not appointment:
            log.warning("appointment_not_found")
            return

        # Update appointment
        appointment.scheduled_at = scheduled_at
        appointment.duration_minutes = duration_minutes
        appointment.sync_status = "synced"
        appointment.last_synced_at = datetime.now(UTC)

        await db.commit()
        await db.refresh(appointment)

        log.info("booking_rescheduled", appointment_id=appointment.id)


async def handle_booking_cancelled(data: dict[str, Any], log: Any) -> None:
    """Handle Cal.com booking cancellation.

    Args:
        data: Cal.com booking data
        log: Logger instance
    """
    booking_uid = data.get("uid", "")

    log = log.bind(booking_uid=booking_uid)
    log.info("processing_booking_cancelled")

    if not booking_uid:
        log.warning("missing_booking_uid")
        return

    async with AsyncSessionLocal() as db:
        # Find appointment by booking UID
        result = await db.execute(
            select(Appointment).where(
                Appointment.calcom_booking_uid == booking_uid,
            )
        )
        appointment = result.scalar_one_or_none()

        if not appointment:
            log.warning("appointment_not_found")
            return

        # Update appointment status
        appointment.status = AppointmentStatus.CANCELLED.value
        appointment.sync_status = "synced"
        appointment.last_synced_at = datetime.now(UTC)
        appointment.sync_error = None  # Clear any previous sync errors

        await db.commit()
        await db.refresh(appointment)

        log.info(
            "booking_cancelled",
            appointment_id=appointment.id,
            status=AppointmentStatus.CANCELLED.value,
        )
