"""Shared reminder-sending logic for appointments.

Extracted from ReminderWorker so that both the background worker and the
manual "send reminder" API endpoint can call the same SMS dispatch path
without duplicating code.
"""

import re
import uuid
import zoneinfo
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog
from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.agent import Agent
from app.models.appointment import Appointment
from app.models.contact import Contact
from app.models.conversation import Conversation, Message, MessageStatus
from app.models.phone_number import PhoneNumber
from app.models.workspace import Workspace
from app.services.idempotency import derive_outbound_key, find_message_by_idempotency_key
from app.services.rate_limiting.opt_out_manager import OptOutManager
from app.services.telephony.telnyx import TelnyxSMSService
from app.services.telephony.text_delivery import TextDeliveryError

logger = structlog.get_logger()

_opt_out_manager = OptOutManager()


# ---------------------------------------------------------------------------
# Phone masking helper
# ---------------------------------------------------------------------------


def mask_phone(phone: str) -> str:
    """Return a masked phone string, e.g. '***-***-1234' (last 4 digits shown)."""
    digits = re.sub(r"\D", "", phone)
    last4 = digits[-4:] if len(digits) >= 4 else digits
    return f"***-***-{last4}"


# ---------------------------------------------------------------------------
# From-number resolution (3-strategy, same as ReminderWorker)
# ---------------------------------------------------------------------------


async def resolve_from_number(
    db: AsyncSession,
    contact_id: int,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID | None,
) -> str | None:
    """Resolve the best from-number for a reminder SMS.

    Strategy 1: Existing conversation workspace_phone (maintains thread).
    Strategy 2: Agent's assigned SMS-enabled phone (if agent provided).
    Strategy 3: Any active SMS-enabled workspace phone (agentless fallback).
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


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


def render_reminder_body(
    template: str | None,
    contact: Contact,
    appointment: Appointment,
    workspace: Workspace,
    agent: Agent | None,
) -> str:
    """Build the SMS body for a reminder.

    If *template* is provided, renders it with standard placeholders:
      {first_name}, {last_name}, {appointment_date}, {appointment_time},
      {appointment_datetime}, {reschedule_link}

    Falls back to a hardcoded default when no template is set.
    Times are formatted in the workspace timezone (falls back to UTC).
    """
    tz_name = (workspace.settings or {}).get("timezone", "UTC")
    try:
        tz = zoneinfo.ZoneInfo(str(tz_name))
    except (KeyError, zoneinfo.ZoneInfoNotFoundError):
        tz = zoneinfo.ZoneInfo("UTC")

    local_dt = appointment.scheduled_at.astimezone(tz)
    date_str = local_dt.strftime("%A, %B %-d")
    time_str = local_dt.strftime("%-I:%M %p")
    datetime_str = f"{date_str} at {time_str}"

    first_name = contact.first_name or "there"

    from app.services.payments.booking_deposit import deposit_message

    if not template:
        return (
            f"Hi {first_name}, just a reminder about your upcoming appointment "
            f"at {time_str}. Check your email for the video call link. "
            f"Reply here if you need to reschedule." + deposit_message(appointment)
        )

    # Build reschedule link if agent has a Cal.com event type configured
    reschedule_link = ""
    if agent is not None and agent.calcom_event_type_id and settings.calcom_api_key:
        try:
            from app.services.calendar.calcom import CalComService

            calcom = CalComService(settings.calcom_api_key)
            contact_name = (
                " ".join(filter(None, [contact.first_name, contact.last_name])) or first_name
            )
            reschedule_link = calcom.generate_booking_url(
                event_type_id=agent.calcom_event_type_id,
                contact_email=contact.email or "",
                contact_name=contact_name,
                contact_phone=contact.phone_number,
            )
        except Exception:
            logger.warning(
                "Could not generate reschedule link for reminder template",
                appointment_id=appointment.id,
            )

    replacements: dict[str, str] = {
        "first_name": contact.first_name or "",
        "last_name": contact.last_name or "",
        "appointment_date": date_str,
        "appointment_time": time_str,
        "appointment_datetime": datetime_str,
        "reschedule_link": reschedule_link,
    }

    message = template
    for placeholder, value in replacements.items():
        try:
            pattern = re.compile(rf"\{{{placeholder}\}}", re.IGNORECASE)
            message = pattern.sub(value, message)
        except Exception:
            logger.warning(
                "Placeholder replacement failed in reminder template",
                placeholder=placeholder,
                appointment_id=appointment.id,
            )

    return message + deposit_message(appointment)


# ---------------------------------------------------------------------------
# Provider acceptance rule (shared by manual + scheduled reminders)
# ---------------------------------------------------------------------------

# Statuses meaning the provider took the message. ``DELIVERED`` only arrives
# later via webhook; callers must not claim delivery from ``SENT``/``SENDING``.
_PROVIDER_ACCEPTED_STATUSES = frozenset(
    {MessageStatus.SENDING, MessageStatus.SENT, MessageStatus.DELIVERED}
)

MANUAL_REMINDER_MAX_ATTEMPTS = 5
SCHEDULED_REMINDER_MAX_ATTEMPTS = 3
_MAX_ERROR_DETAIL = 200


class ReminderSendStatus(StrEnum):
    """Outcome of one reminder send attempt."""

    ACCEPTED = "accepted"  # provider accepted a new message on this call
    ALREADY_ACCEPTED = "already_accepted"  # an earlier attempt was accepted; nothing sent
    FAILED = "failed"  # provider rejected/failed this attempt; a retry may follow
    EXHAUSTED = "exhausted"  # every allowed attempt failed; nothing sent


@dataclass(frozen=True, slots=True)
class ReminderSendResult:
    status: ReminderSendStatus
    message: Message | None
    attempt: int
    max_attempts: int
    error: str | None = None

    @property
    def accepted(self) -> bool:
        return self.status in {ReminderSendStatus.ACCEPTED, ReminderSendStatus.ALREADY_ACCEPTED}

    @property
    def is_final_failure(self) -> bool:
        """True when no further attempt will be made for this reminder."""
        return self.status is ReminderSendStatus.EXHAUSTED or (
            self.status is ReminderSendStatus.FAILED and self.attempt + 1 >= self.max_attempts
        )


def is_provider_accepted(message: Message) -> bool:
    """Return True when ``message`` was accepted by the messaging provider.

    Failed text attempts raise at the provider boundary. This check also
    supports persisted history and result adapters before updating reminder flags.
    """
    return message.status in _PROVIDER_ACCEPTED_STATUSES


def reminder_attempt_key(scope_parts: tuple[object, ...], attempt: int) -> uuid.UUID:
    """Idempotency key for reminder ``attempt``.

    Attempt 0 keeps the historical key so in-flight rows still dedupe; later
    attempts get distinct keys because the provider already consumed (and
    rejected) the earlier ones.
    """
    scope, *parts = scope_parts
    if attempt == 0:
        return derive_outbound_key(str(scope), *parts)
    return derive_outbound_key(str(scope), *parts, "attempt", attempt)


async def send_reminder_sms(
    *,
    db: AsyncSession,
    sms_service: TelnyxSMSService,
    scope_parts: tuple[object, ...],
    to_number: str,
    from_number: str,
    body: str,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID | None,
    max_attempts: int,
) -> ReminderSendResult:
    """Send at most one reminder SMS, honouring prior attempts.

    Walks the attempt keys in order: an accepted message under any key means the
    reminder already went out (no resend); a failed one advances to the next
    key; a missing or still-``queued`` row is (re)sent under that key. Errors
    raised before the provider responds propagate to the caller.
    """
    for attempt in range(max_attempts):
        key = reminder_attempt_key(scope_parts, attempt)
        existing = await find_message_by_idempotency_key(db, key)
        if existing is not None:
            if is_provider_accepted(existing):
                return ReminderSendResult(
                    ReminderSendStatus.ALREADY_ACCEPTED, existing, attempt, max_attempts
                )
            if existing.status != MessageStatus.QUEUED:
                continue  # this attempt failed; try the next key

        try:
            message = await sms_service.send_message(
                to_number=to_number,
                from_number=from_number,
                body=body,
                db=db,
                workspace_id=workspace_id,
                agent_id=agent_id,
                idempotency_key=key,
            )
        except TextDeliveryError as exc:
            return ReminderSendResult(
                ReminderSendStatus.FAILED,
                exc.failed_message,
                attempt,
                max_attempts,
                error=exc.message,
            )
        if is_provider_accepted(message):
            return ReminderSendResult(ReminderSendStatus.ACCEPTED, message, attempt, max_attempts)
        error = (message.error_message or "Provider did not accept the message")[:_MAX_ERROR_DETAIL]
        return ReminderSendResult(
            ReminderSendStatus.FAILED, message, attempt, max_attempts, error=error
        )

    return ReminderSendResult(ReminderSendStatus.EXHAUSTED, None, max_attempts, max_attempts)


# ---------------------------------------------------------------------------
# Core send function
# ---------------------------------------------------------------------------


def _manual_unsent_payload(
    result: ReminderSendResult, contact_phone: str, log: Any
) -> dict[str, Any]:
    """Response for a manual reminder that did not send a new message."""
    if result.status is ReminderSendStatus.ALREADY_ACCEPTED:
        log.info("manual_reminder_already_sent", attempt=result.attempt + 1)
        return {
            "success": True,
            "status": "already_sent",
            "message": "A reminder was already sent for this appointment",
            "sent_to": mask_phone(contact_phone),
            "retryable": False,
        }

    if result.status is ReminderSendStatus.EXHAUSTED:
        log.warning("manual_reminder_attempts_exhausted", max_attempts=result.max_attempts)
        return {
            "success": False,
            "status": "failed",
            "message": (
                f"Reminder failed {result.max_attempts} times and was not sent. "
                "Check the contact's phone number and your sending number, "
                "or reach the contact another way."
            ),
            "sent_to": None,
            "retryable": False,
        }

    if result.status is ReminderSendStatus.FAILED:
        retryable = not result.is_final_failure
        log.warning(
            "manual_reminder_rejected",
            message_id=str(result.message.id) if result.message else None,
            attempt=result.attempt + 1,
            error=result.error,
        )
        hint = (
            "You can try again."
            if retryable
            else "Check the contact's phone number and your sending number."
        )
        return {
            "success": False,
            "status": "failed",
            "message": f"Reminder was not sent: {result.error}. {hint}",
            "sent_to": None,
            "retryable": retryable,
        }

    msg = f"unexpected reminder status {result.status}"
    raise ValueError(msg)


async def send_appointment_reminder(
    db: AsyncSession,
    appointment: Appointment,
    workspace: Workspace,
    contact: Contact,
    agent: Agent | None,
) -> dict[str, Any]:
    """Send a manual SMS reminder for an appointment.

    Returns a dict with:
      - ``success``: bool — True only when the provider accepted a reminder
      - ``status``: ``sent`` | ``already_sent`` | ``failed`` | ``not_sent``
      - ``message``: human-readable description
      - ``sent_to``: masked phone string on success, None on failure
      - ``retryable``: whether pressing send again can make a new attempt

    ``reminder_sent_at`` is only updated when the provider accepts a new
    message. "Sent" means accepted by the provider, not delivered.
    """
    log = logger.bind(appointment_id=appointment.id, trigger="manual")

    telnyx_key = settings.telnyx_api_key
    contact_phone = contact.phone_number
    if not contact_phone:
        log.warning("contact_has_no_phone", contact_id=contact.id)
        return {
            "success": False,
            "status": "not_sent",
            "message": "Contact has no phone number",
            "sent_to": None,
            "retryable": False,
        }

    # TCPA compliance — skip opted-out contacts
    is_opted_out = await _opt_out_manager.check_opt_out(workspace.id, contact_phone, db)
    if is_opted_out:
        log.info("contact_opted_out", contact_id=contact.id)
        return {
            "success": False,
            "status": "not_sent",
            "message": "Contact has opted out of SMS",
            "sent_to": None,
            "retryable": False,
        }

    agent_id = agent.id if agent is not None else None

    from_number = await resolve_from_number(db, contact.id, workspace.id, agent_id)
    if not from_number:
        log.warning("could_not_resolve_from_number")
        return {
            "success": False,
            "status": "not_sent",
            "message": "Could not find a sending phone number for this workspace",
            "sent_to": None,
            "retryable": False,
        }

    body = render_reminder_body(
        template=agent.reminder_template if agent is not None else None,
        contact=contact,
        appointment=appointment,
        workspace=workspace,
        agent=agent,
    )

    sms_service = TelnyxSMSService(telnyx_key)
    try:
        result = await send_reminder_sms(
            db=db,
            sms_service=sms_service,
            scope_parts=("manual_appointment_reminder", appointment.id),
            to_number=contact_phone,
            from_number=from_number,
            body=body,
            workspace_id=workspace.id,
            agent_id=agent_id,
            max_attempts=MANUAL_REMINDER_MAX_ATTEMPTS,
        )

        if result.status is not ReminderSendStatus.ACCEPTED:
            return _manual_unsent_payload(result, contact_phone, log)

        log.info(
            "manual_reminder_sent",
            message_id=str(result.message.id) if result.message else None,
            attempt=result.attempt + 1,
        )

        # Update reminder_sent_at without touching reminders_sent (offset tracking)
        now = datetime.now(UTC)
        await db.execute(
            text("UPDATE appointments SET reminder_sent_at = :now WHERE id = :appt_id"),
            {"now": now, "appt_id": appointment.id},
        )
        appointment.reminder_sent_at = now
        await db.commit()

        return {
            "success": True,
            "status": "sent",
            "message": "Reminder sent",
            "sent_to": mask_phone(contact_phone),
            "retryable": False,
        }

    except Exception as exc:
        log.exception("failed_to_send_manual_reminder", error=str(exc))
        raise
    finally:
        await sms_service.close()
