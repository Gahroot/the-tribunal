"""Appointment reminder worker.

Sends SMS reminders before scheduled appointments using the same phone number
the contact was originally reached on, ensuring a seamless conversation thread.
"""

import uuid
import zoneinfo
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.appointment import Appointment
from app.models.conversation import Conversation
from app.models.phone_number import PhoneNumber
from app.services.telephony.telnyx import TelnyxSMSService
from app.workers.base import BaseWorker, WorkerRegistry

MAX_REMINDERS_PER_TICK = 20


class ReminderWorker(BaseWorker):
    """Background worker for sending appointment reminders via SMS."""

    POLL_INTERVAL_SECONDS = 60
    COMPONENT_NAME = "reminder_worker"

    async def _process_items(self) -> None:
        """Find and send due appointment reminders."""
        async with AsyncSessionLocal() as db:
            now = datetime.now(UTC)

            # Broad window: fetch appointments within the next 60 minutes
            # that haven't had a reminder sent yet
            result = await db.execute(
                select(Appointment)
                .options(
                    joinedload(Appointment.agent),
                    joinedload(Appointment.contact),
                    joinedload(Appointment.workspace),
                )
                .where(
                    and_(
                        Appointment.status == "scheduled",
                        Appointment.reminder_sent_at.is_(None),
                        Appointment.scheduled_at > now,
                        Appointment.scheduled_at <= now + timedelta(minutes=60),
                        Appointment.agent_id.is_not(None),
                        Appointment.contact_id.is_not(None),
                    )
                )
                .order_by(Appointment.scheduled_at)
                .limit(MAX_REMINDERS_PER_TICK)
            )
            appointments = result.unique().scalars().all()

            if not appointments:
                return

            # Filter by each agent's reminder config
            due: list[Appointment] = []
            for appt in appointments:
                agent = appt.agent
                if agent is None or not agent.reminder_enabled:
                    continue
                threshold = now + timedelta(minutes=agent.reminder_minutes_before)
                if appt.scheduled_at <= threshold:
                    due.append(appt)

            if not due:
                return

            self.logger.info("Processing appointment reminders", count=len(due))

            for appt in due:
                try:
                    await self._send_reminder(appt, db)
                except Exception:
                    self.logger.exception(
                        "Error sending appointment reminder",
                        appointment_id=appt.id,
                    )

    async def _send_reminder(
        self,
        appt: Appointment,
        db: AsyncSession,
    ) -> None:
        """Send a single appointment reminder SMS."""
        log = self.logger.bind(appointment_id=appt.id)
        agent = appt.agent
        contact = appt.contact
        workspace = appt.workspace

        if agent is None or contact is None or workspace is None:
            log.warning("Missing agent, contact, or workspace")
            return

        telnyx_key = settings.telnyx_api_key
        if not telnyx_key:
            log.warning("No Telnyx API key configured")
            return

        contact_phone = contact.phone_number
        if not contact_phone:
            log.warning("Contact has no phone number")
            return

        # Resolve the from number
        from_number = await self._resolve_from_number(
            db, contact.id, workspace.id, agent.id
        )
        if not from_number:
            log.warning("Could not resolve from number, will retry next tick")
            return

        # Format time in workspace timezone or UTC
        tz_name = (workspace.settings or {}).get("timezone", "UTC")
        try:
            tz = zoneinfo.ZoneInfo(tz_name)
        except (KeyError, zoneinfo.ZoneInfoNotFoundError):
            tz = zoneinfo.ZoneInfo("UTC")

        local_time = appt.scheduled_at.astimezone(tz)
        time_str = local_time.strftime("%-I:%M %p")

        first_name = contact.first_name or "there"
        body = (
            f"Hi {first_name}, just a reminder about your upcoming appointment "
            f"at {time_str}. Check your email for the video call link. "
            f"Reply here if you need to reschedule."
        )

        sms_service = TelnyxSMSService(telnyx_key)
        try:
            message = await sms_service.send_message(
                to_number=contact_phone,
                from_number=from_number,
                body=body,
                db=db,
                workspace_id=workspace.id,
                agent_id=agent.id,
            )

            log.info("Appointment reminder sent", message_id=str(message.id))

            # Mark reminder as sent
            appt.reminder_sent_at = datetime.now(UTC)

            # Ensure the conversation is assigned to the booking agent with AI enabled
            conv_result = await db.execute(
                select(Conversation).where(
                    and_(
                        Conversation.workspace_phone == from_number,
                        Conversation.contact_phone == contact_phone,
                        Conversation.workspace_id == workspace.id,
                    )
                )
                .order_by(Conversation.updated_at.desc())
                .limit(1)
            )
            conversation = conv_result.scalars().first()
            if conversation:
                conversation.assigned_agent_id = agent.id
                conversation.ai_enabled = True

            await db.commit()

        except Exception as e:
            log.exception("Failed to send reminder SMS", error=str(e))
        finally:
            await sms_service.close()

    async def _resolve_from_number(
        self,
        db: AsyncSession,
        contact_id: int,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
    ) -> str | None:
        """Resolve the best from-number for the reminder.

        Strategy 1: Find existing conversation with this contact (reuse same number).
        Strategy 2: Fall back to agent's assigned phone number.
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

        return None


# Singleton registry
_registry = WorkerRegistry(ReminderWorker)
start_reminder_worker = _registry.start
stop_reminder_worker = _registry.stop
get_reminder_worker = _registry.get
