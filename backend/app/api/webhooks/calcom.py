"""Cal.com webhook endpoints for appointment events."""

import re
import uuid
import zoneinfo
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from fastapi import APIRouter, Request
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.webhook_security import verify_calcom_webhook
from app.db.session import AsyncSessionLocal
from app.models.agent import Agent
from app.models.appointment import Appointment, AppointmentStatus
from app.models.campaign import Campaign, CampaignContact
from app.models.contact import Contact
from app.models.conversation import Conversation, Message
from app.models.phone_number import PhoneNumber
from app.models.workspace import Workspace
from app.services.campaigns.guarantee_tracker import increment_completed_and_check_guarantee
from app.services.rate_limiting.opt_out_manager import OptOutManager
from app.services.telephony.telnyx import TelnyxSMSService

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
    elif trigger == "MEETING_ENDED":
        await handle_meeting_ended(data, log)
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


async def _resolve_campaign_id(db: Any, contact_id: int, log: Any) -> Any:
    """Find the most recent active campaign for a contact."""
    try:
        cc_result = await db.execute(
            select(CampaignContact.campaign_id)
            .join(Campaign, CampaignContact.campaign_id == Campaign.id)
            .where(
                CampaignContact.contact_id == contact_id,
                Campaign.status.in_(["running", "paused"]),
            )
            .order_by(CampaignContact.created_at.desc())
            .limit(1)
        )
        cc_row = cc_result.first()
        if cc_row:
            log.info("resolved_campaign_for_appointment", campaign_id=str(cc_row[0]))
            return cc_row[0]
    except Exception as e:
        log.warning("campaign_resolution_failed", error=str(e))
    return None


_DEFAULT_CONFIRMATION_BODY = (
    "Hi {first_name}! Your appointment is confirmed for {appointment_date} at "
    "{appointment_time}. We'll send you a reminder beforehand. "
    "Reply here if you need to reschedule."
)


async def _resolve_sms_from_number(
    db: AsyncSession,
    contact_id: int,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID | None,
) -> str | None:
    """Resolve the best from-number for a lifecycle SMS.

    Strategy 1: Reuse an existing conversation with this contact.
    Strategy 2: Fall back to the agent's assigned SMS-enabled phone number.
    Strategy 3: Fall back to any active SMS-enabled workspace phone number.
    """
    # Strategy 1 — existing conversation
    result = await db.execute(
        select(Conversation.workspace_phone)
        .where(
            and_(
                Conversation.contact_id == contact_id,
                Conversation.workspace_id == workspace_id,
            )
        )
        .order_by(Conversation.last_message_at.desc().nulls_last())
        .limit(1)
    )
    phone = result.scalar_one_or_none()
    if phone:
        return str(phone)

    # Strategy 2 — agent's assigned phone number
    if agent_id is not None:
        result = await db.execute(
            select(PhoneNumber.phone_number)
            .where(
                and_(
                    PhoneNumber.assigned_agent_id == agent_id,
                    PhoneNumber.is_active.is_(True),
                    PhoneNumber.sms_enabled.is_(True),
                )
            )
            .limit(1)
        )
        phone = result.scalar_one_or_none()
        if phone:
            return str(phone)

    # Strategy 3 — any active SMS-enabled workspace phone number
    result = await db.execute(
        select(PhoneNumber.phone_number)
        .where(
            and_(
                PhoneNumber.workspace_id == workspace_id,
                PhoneNumber.is_active.is_(True),
                PhoneNumber.sms_enabled.is_(True),
            )
        )
        .order_by(PhoneNumber.created_at)
        .limit(1)
    )
    phone = result.scalar_one_or_none()
    if phone:
        return str(phone)

    return None


def _build_confirmation_body(
    contact: Contact,
    appointment: Appointment,
    workspace: Workspace | None,
    agent: Agent | None,
) -> str:
    """Build the confirmation SMS body.

    Uses agent.reminder_template when set (note: this is the reminder template
    repurposed for confirmation; a dedicated confirmation_template field may be
    added in a future iteration). Falls back to _DEFAULT_CONFIRMATION_BODY.

    Times are formatted in the workspace timezone (falls back to UTC).
    """
    # Resolve timezone
    tz_name = ((workspace.settings if workspace else None) or {}).get("timezone", "UTC")
    try:
        tz = zoneinfo.ZoneInfo(str(tz_name))
    except (KeyError, zoneinfo.ZoneInfoNotFoundError):
        tz = zoneinfo.ZoneInfo("UTC")

    local_dt = appointment.scheduled_at.astimezone(tz)
    date_str = local_dt.strftime("%A, %B %-d")  # e.g. "Monday, March 24"
    time_str = local_dt.strftime("%-I:%M %p")   # e.g. "3:00 PM"

    first_name = contact.first_name or "there"
    template = agent.reminder_template if agent is not None else None

    if not template:
        return _DEFAULT_CONFIRMATION_BODY.format(
            first_name=first_name,
            appointment_date=date_str,
            appointment_time=time_str,
        )

    # Build reschedule link if agent has a Cal.com event type configured
    reschedule_link = ""
    if agent is not None and agent.calcom_event_type_id and settings.calcom_api_key:
        try:
            from app.services.calendar.calcom import CalComService

            calcom = CalComService(settings.calcom_api_key)
            contact_name = " ".join(
                filter(None, [contact.first_name, contact.last_name])
            ) or first_name
            reschedule_link = calcom.generate_booking_url(
                event_type_id=agent.calcom_event_type_id,
                contact_email=contact.email or "",
                contact_name=contact_name,
                contact_phone=contact.phone_number,
            )
        except Exception:
            logger.warning(
                "confirmation_sms_reschedule_link_failed",
                appointment_id=appointment.id,
            )

    replacements: dict[str, str] = {
        "first_name": contact.first_name or "",
        "last_name": contact.last_name or "",
        "appointment_date": date_str,
        "appointment_time": time_str,
        "appointment_datetime": f"{date_str} at {time_str}",
        "reschedule_link": reschedule_link,
    }

    message = template
    for placeholder, value in replacements.items():
        try:
            pattern = re.compile(rf"\{{{placeholder}\}}", re.IGNORECASE)
            message = pattern.sub(value, message)
        except Exception:
            pass  # Non-fatal; leave placeholder as-is

    return message


async def _send_lifecycle_sms(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    contact: Contact,
    agent: Agent | None,
    body_text: str,
) -> None:
    """Send a lifecycle SMS (confirmation, cancellation, etc.) to a contact.

    This is a shared helper used by all lifecycle SMS touch-points. It:
    - Checks contact has a phone number
    - Resolves the from-number (existing convo > agent number > workspace number)
    - Checks TCPA opt-out compliance before sending
    - Sends via TelnyxSMSService
    - Logs success/failure at appropriate levels
    - Is entirely wrapped in try/except — never raises, caller always gets None

    Args:
        db: Active database session (must be open; this helper may commit).
        workspace_id: Workspace UUID.
        contact: Contact ORM object (needs .phone_number, .id).
        agent: Optional Agent ORM object (used for from-number resolution).
        body_text: Pre-rendered SMS body text.
    """
    try:
        telnyx_key = settings.telnyx_api_key
        if not telnyx_key:
            logger.warning("lifecycle_sms_no_telnyx_key", contact_id=contact.id)
            return

        contact_phone = contact.phone_number
        if not contact_phone:
            logger.debug("lifecycle_sms_skipped_no_phone", contact_id=contact.id)
            return

        agent_id = agent.id if agent is not None else None

        # TCPA compliance — respect opt-outs
        opt_out_manager = OptOutManager()
        is_opted_out = await opt_out_manager.check_opt_out(workspace_id, contact_phone, db)
        if is_opted_out:
            logger.info(
                "lifecycle_sms_skipped_opted_out",
                contact_id=contact.id,
                phone=contact_phone,
            )
            return

        from_number = await _resolve_sms_from_number(db, contact.id, workspace_id, agent_id)
        if not from_number:
            logger.warning(
                "lifecycle_sms_no_from_number",
                contact_id=contact.id,
                workspace_id=str(workspace_id),
            )
            return

        sms_service = TelnyxSMSService(telnyx_key)
        try:
            message = await sms_service.send_message(
                to_number=contact_phone,
                from_number=from_number,
                body=body_text,
                db=db,
                workspace_id=workspace_id,
                agent_id=agent_id,
            )
            logger.info(
                "lifecycle_sms_sent",
                contact_id=contact.id,
                message_id=str(message.id),
            )
        finally:
            await sms_service.close()

    except Exception as e:
        logger.exception(
            "lifecycle_sms_failed",
            contact_id=contact.id,
            error=str(e),
        )


async def handle_booking_created(data: dict[str, Any], log: Any) -> None:  # noqa: PLR0912, PLR0915
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
            return

        workspace_id = contact.workspace_id
        campaign_id_val = await _resolve_campaign_id(db, contact.id, log)

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
        is_new_booking = appointment is None  # Track before upsert

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
                campaign_id=campaign_id_val,
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

        # Send confirmation SMS immediately for new bookings only.
        # Wrapped in _send_lifecycle_sms which never raises — webhook always
        # returns 200 regardless of SMS outcome.
        if is_new_booking:
            # Fetch workspace to resolve timezone for time formatting
            ws_result = await db.execute(
                select(Workspace).where(Workspace.id == workspace_id)
            )
            workspace = ws_result.scalar_one_or_none()

            confirmation_body = _build_confirmation_body(
                contact=contact,
                appointment=appointment,
                workspace=workspace,
                agent=agent,
            )
            log.info(
                "sending_booking_confirmation_sms",
                contact_id=contact.id,
                appointment_id=appointment.id,
            )
            await _send_lifecycle_sms(
                db=db,
                workspace_id=workspace_id,
                contact=contact,
                agent=agent,
                body_text=confirmation_body,
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

        # Reset reminder tracking so the reminder worker re-fires for the new time
        appointment.reminder_sent_at = None
        log.info(
            "reminder_tracking_reset_for_rescheduled_appointment",
            uid=booking_uid,
        )

        await db.commit()
        await db.refresh(appointment)

        log.info("booking_rescheduled", appointment_id=appointment.id)

        # Send rescheduled notification SMS — failures must not affect the webhook response
        try:
            contact_result = await db.execute(
                select(Contact).where(Contact.id == appointment.contact_id)
            )
            contact = contact_result.scalar_one_or_none()

            if contact:
                # Load agent (optional — used for from-number resolution)
                rescheduled_agent: Agent | None = None
                if appointment.agent_id:
                    agent_result = await db.execute(
                        select(Agent).where(Agent.id == appointment.agent_id)
                    )
                    rescheduled_agent = agent_result.scalar_one_or_none()

                # Load workspace for timezone formatting
                ws_result = await db.execute(
                    select(Workspace).where(Workspace.id == contact.workspace_id)
                )
                workspace = ws_result.scalar_one_or_none()

                # Format new date/time in workspace timezone
                tz_name = (
                    ((workspace.settings if workspace else None) or {}).get("timezone", "UTC")
                )
                try:
                    tz = zoneinfo.ZoneInfo(str(tz_name))
                except (KeyError, zoneinfo.ZoneInfoNotFoundError):
                    tz = zoneinfo.ZoneInfo("UTC")

                local_dt = appointment.scheduled_at.astimezone(tz)
                new_date = local_dt.strftime("%A, %B %-d")  # e.g. "Monday, March 24"
                new_time = local_dt.strftime("%-I:%M %p")   # e.g. "3:00 PM"

                first_name = contact.first_name or "there"
                rescheduled_body = (
                    f"Hi {first_name}, your appointment has been rescheduled to "
                    f"{new_date} at {new_time}. See you then! "
                    "Reply here if you need to make any changes."
                )

                log.info(
                    "sending_rescheduled_notification_sms",
                    contact_id=contact.id,
                    appointment_id=appointment.id,
                )
                await _send_lifecycle_sms(
                    db=db,
                    workspace_id=contact.workspace_id,
                    contact=contact,
                    agent=rescheduled_agent,
                    body_text=rescheduled_body,
                )
        except Exception as e:
            log.warning("rescheduled_sms_setup_failed", error=str(e))


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

    # Determine if cancellation was host-initiated.
    # Cal.com sets `cancelledBy` to the email of the actor who cancelled.
    # If it matches the organizer email, the host cancelled — skip the rebook SMS.
    cancelled_by_email: str = (data.get("cancelledBy") or "").strip().lower()
    organizer_email: str = (data.get("organizer", {}).get("email") or "").strip().lower()
    is_host_initiated = bool(
        cancelled_by_email and organizer_email and cancelled_by_email == organizer_email
    )

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
            is_host_initiated=is_host_initiated,
        )

        # Send rebook SMS for attendee-initiated cancellations only.
        # Host-initiated cancellations are intentional — no rebook prompt needed.
        # Wrapped in try/except — never affects the webhook response.
        if not is_host_initiated:
            try:
                contact_result = await db.execute(
                    select(Contact).where(Contact.id == appointment.contact_id)
                )
                cancelled_contact = contact_result.scalar_one_or_none()

                if cancelled_contact:
                    # Load agent (used for rebook URL generation + from-number resolution)
                    cancelled_agent: Agent | None = None
                    if appointment.agent_id:
                        agent_result = await db.execute(
                            select(Agent).where(Agent.id == appointment.agent_id)
                        )
                        cancelled_agent = agent_result.scalar_one_or_none()

                    first_name = cancelled_contact.first_name or "there"

                    # Generate rebook URL if agent has a Cal.com event type configured
                    rebook_url: str | None = None
                    if (
                        cancelled_agent is not None
                        and cancelled_agent.calcom_event_type_id
                        and settings.calcom_api_key
                    ):
                        try:
                            from app.services.calendar.calcom import CalComService

                            calcom = CalComService(settings.calcom_api_key)
                            contact_name = " ".join(
                                filter(
                                    None,
                                    [cancelled_contact.first_name, cancelled_contact.last_name],
                                )
                            ) or first_name
                            rebook_url = calcom.generate_booking_url(
                                event_type_id=cancelled_agent.calcom_event_type_id,
                                contact_email=cancelled_contact.email or "",
                                contact_name=contact_name,
                                contact_phone=cancelled_contact.phone_number,
                            )
                        except Exception:
                            log.warning(
                                "cancellation_sms_rebook_url_failed",
                                appointment_id=appointment.id,
                            )

                    if rebook_url:
                        cancellation_body = (
                            f"Hi {first_name}, your appointment has been cancelled. "
                            f"We\u2019d love to find another time that works for you \u2014 "
                            f"book here: {rebook_url}. "
                            "Or reply to this message and we\u2019ll help you reschedule."
                        )
                    else:
                        cancellation_body = (
                            f"Hi {first_name}, your appointment has been cancelled. "
                            "We\u2019d love to find another time that works for you. "
                            "Reply to this message and we\u2019ll help you reschedule."
                        )

                    log.info(
                        "sending_cancellation_rebook_sms",
                        contact_id=cancelled_contact.id,
                        appointment_id=appointment.id,
                        has_rebook_url=rebook_url is not None,
                    )
                    await _send_lifecycle_sms(
                        db=db,
                        workspace_id=cancelled_contact.workspace_id,
                        contact=cancelled_contact,
                        agent=cancelled_agent,
                        body_text=cancellation_body,
                    )
            except Exception as e:
                log.warning("cancellation_sms_setup_failed", error=str(e))


async def handle_meeting_ended(data: dict[str, Any], log: Any) -> None:  # noqa: PLR0912, PLR0915
    """Handle Cal.com MEETING_ENDED event.

    Marks appointments as completed or no_show based on meeting data.
    """
    booking_uid = data.get("uid", "")

    log = log.bind(booking_uid=booking_uid)
    log.info("processing_meeting_ended")

    if not booking_uid:
        log.warning("missing_booking_uid")
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Appointment).where(
                Appointment.calcom_booking_uid == booking_uid,
            )
        )
        appointment = result.scalar_one_or_none()

        if not appointment:
            log.warning("appointment_not_found")
            return

        # Skip if already in terminal state
        if appointment.status in (
            AppointmentStatus.COMPLETED.value,
            AppointmentStatus.CANCELLED.value,
        ):
            log.info("appointment_already_terminal", status=appointment.status)
            return

        # Determine if completed or no-show
        no_show_host = data.get("noShowHost", False)
        attendees = data.get("attendees", [])

        if no_show_host or not attendees:
            appointment.status = AppointmentStatus.NO_SHOW.value
            log.info("appointment_no_show", appointment_id=appointment.id)
        else:
            appointment.status = AppointmentStatus.COMPLETED.value
            log.info("appointment_completed", appointment_id=appointment.id)

            # Update campaign guarantee tracking
            if appointment.campaign_id:
                await increment_completed_and_check_guarantee(
                    db, appointment.campaign_id, log
                )

        appointment.sync_status = "synced"
        appointment.last_synced_at = datetime.now(UTC)

        is_no_show = appointment.status == AppointmentStatus.NO_SHOW.value

        await db.commit()

        log.info(
            "meeting_ended_processed",
            appointment_id=appointment.id,
            status=appointment.status,
        )

        # Send no-show re-engagement SMS with rebook link.
        # Wrapped in try/except — never affects the webhook response.
        if is_no_show:
            try:
                contact_result = await db.execute(
                    select(Contact).where(Contact.id == appointment.contact_id)
                )
                noshow_contact = contact_result.scalar_one_or_none()

                if noshow_contact:
                    # Load agent (used for noshow_sms_enabled flag + rebook URL)
                    noshow_agent: Agent | None = None
                    if appointment.agent_id:
                        agent_result = await db.execute(
                            select(Agent).where(Agent.id == appointment.agent_id)
                        )
                        noshow_agent = agent_result.scalar_one_or_none()

                    # Respect agent-level toggle (default True when no agent)
                    sms_enabled = (
                        noshow_agent.noshow_sms_enabled
                        if noshow_agent is not None
                        else True
                    )
                    if not sms_enabled:
                        log.info(
                            "noshow_sms_disabled_for_agent",
                            agent_id=str(appointment.agent_id),
                        )
                    else:
                        first_name = noshow_contact.first_name or "there"

                        # Generate rebook URL if possible
                        booking_url: str | None = None
                        if (
                            noshow_agent is not None
                            and noshow_agent.calcom_event_type_id
                            and settings.calcom_api_key
                        ):
                            try:
                                from app.services.calendar.calcom import CalComService

                                calcom = CalComService(settings.calcom_api_key)
                                contact_name = " ".join(
                                    filter(
                                        None,
                                        [noshow_contact.first_name, noshow_contact.last_name],
                                    )
                                ) or first_name
                                booking_url = calcom.generate_booking_url(
                                    event_type_id=noshow_agent.calcom_event_type_id,
                                    contact_email=noshow_contact.email or "",
                                    contact_name=contact_name,
                                    contact_phone=noshow_contact.phone_number,
                                )
                            except Exception:
                                log.warning(
                                    "noshow_sms_rebook_url_failed",
                                    appointment_id=appointment.id,
                                )

                        if booking_url:
                            noshow_body = (
                                f"Hi {first_name}, we missed you at your appointment today. "
                                f"No worries \u2014 would you like to find another time? "
                                f"Book here: {booking_url}"
                            )
                        else:
                            noshow_body = (
                                f"Hi {first_name}, we missed you at your appointment today. "
                                f"No worries \u2014 would you like to find another time? "
                                "Reply here to rebook."
                            )

                        log.info(
                            "sending_noshow_reengagement_sms",
                            contact_id=noshow_contact.id,
                            appointment_id=appointment.id,
                            has_rebook_url=booking_url is not None,
                        )
                        await _send_lifecycle_sms(
                            db=db,
                            workspace_id=noshow_contact.workspace_id,
                            contact=noshow_contact,
                            agent=noshow_agent,
                            body_text=noshow_body,
                        )
            except Exception as e:
                log.warning("noshow_sms_setup_failed", error=str(e))
