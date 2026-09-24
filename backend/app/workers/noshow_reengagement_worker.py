"""No-show re-engagement worker.

Runs a multi-day drip sequence for contacts who missed their appointment:
  - Day 3 (> 2 days after no-show): send agent.noshow_day3_template
  - Day 7 (> 6 days after no-show, Day-3 already sent): send agent.noshow_day7_template

Progress is tracked via normalized contact tags:
  - "noshow-day3-sent"  — Day-3 message has been delivered
  - "noshow-day7-sent"  — Day-7 message has been delivered
  - "reengaged-booked"  — contact rebooked; stop all re-engagement

The worker resolves the best from-number using the same 3-strategy approach
as the reminder worker and respects the workspace opt-out list.
"""

import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.agent import Agent
from app.models.appointment import Appointment, AppointmentStatus
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.phone_number import PhoneNumber
from app.models.tag import ContactTag, Tag
from app.services.idempotency import derive_outbound_key, derive_worker_retry_key
from app.services.rate_limiting.opt_out_manager import OptOutManager
from app.services.tags import TagService
from app.services.telephony.telnyx import TelnyxSMSService
from app.workers.base import BaseWorker, WorkerRegistry
from app.workers.retryable import RetryableWorker

MAX_CONTACTS_PER_TICK = 20

# Default templates used when the agent has not configured a custom one
_DEFAULT_DAY3_TEMPLATE = "Hey {first_name}, {reengagement_message} {reschedule_link}"
_DEFAULT_DAY7_TEMPLATE = "Hi {first_name}, {reengagement_message} {reschedule_link}"

_CAUSE_COPY = {
    "noshow-confirmed-then-no-show": (
        "we know plans can change even after confirming. Want to find another time?",
        "would another time work better for you? Book here:",
    ),
    "noshow-never-confirmed": (
        "we weren't able to confirm your last appointment. Is there a better time to connect?",
        "if the earlier time didn't work, you can choose a better one here:",
    ),
}


class NoshowReengagementWorker(RetryableWorker, BaseWorker):
    """Background worker for no-show multi-day re-engagement sequences."""

    POLL_INTERVAL_SECONDS = 3600  # once per hour
    COMPONENT_NAME = "noshow_reengagement_worker"
    # Per-contact SMS step in a re-engagement sequence.
    MAX_CONCURRENCY = 5
    max_retries = 3
    backoff_base_seconds = 2.0

    def __init__(self) -> None:
        super().__init__()
        self.opt_out_manager = OptOutManager()

    async def _process_items(self) -> None:
        """Process all pending no-show re-engagement messages."""
        async with AsyncSessionLocal() as db:
            # Fetch all agents with re-engagement enabled
            agent_result = await db.execute(
                select(Agent).where(Agent.noshow_reengagement_enabled.is_(True))
            )
            agents = agent_result.scalars().all()

            if not agents:
                return

            for agent in agents:
                await self.execute_with_retry(
                    self._process_agent,
                    agent,
                    db,
                    item_key=derive_worker_retry_key("agent", agent.id),
                )

    async def _process_agent(self, agent: Agent, db: AsyncSession) -> None:
        """Process re-engagement for all qualifying contacts of one agent."""
        now = datetime.now(UTC)
        day3_cutoff = now - timedelta(days=2)  # updated_at < this → past Day 3
        day7_cutoff = now - timedelta(days=6)  # updated_at < this → past Day 7

        # --- Day-3 contacts ---
        # No-show status, no "reengaged-booked" tag, no "noshow-day3-sent" tag
        # updated_at (when last_appointment_status was set) > 2 days ago
        day3_result = await db.execute(
            select(Contact)
            .where(
                and_(
                    Contact.workspace_id == agent.workspace_id,
                    Contact.last_appointment_status == "no_show",
                    Contact.updated_at <= day3_cutoff,
                    self._has_tag(agent.workspace_id, "no-show"),
                    ~self._has_any_tag(
                        agent.workspace_id,
                        ["noshow-day3-sent", "reengaged-booked"],
                    ),
                )
            )
            .order_by(Contact.updated_at)
            .limit(MAX_CONTACTS_PER_TICK)
        )
        day3_contacts = day3_result.scalars().all()

        # --- Day-7 contacts ---
        # Day-3 already sent, but Day-7 not yet, still no rebook
        day7_result = await db.execute(
            select(Contact)
            .where(
                and_(
                    Contact.workspace_id == agent.workspace_id,
                    Contact.last_appointment_status == "no_show",
                    Contact.updated_at <= day7_cutoff,
                    self._has_tag(agent.workspace_id, "noshow-day3-sent"),
                    ~self._has_any_tag(
                        agent.workspace_id,
                        ["noshow-day7-sent", "reengaged-booked"],
                    ),
                )
            )
            .order_by(Contact.updated_at)
            .limit(MAX_CONTACTS_PER_TICK)
        )
        day7_contacts = day7_result.scalars().all()

        total = len(day3_contacts) + len(day7_contacts)
        if total:
            self.logger.info(
                "Processing noshow re-engagement",
                agent_id=str(agent.id),
                day3_count=len(day3_contacts),
                day7_count=len(day7_contacts),
            )

        for contact in day3_contacts:
            # If they rebooked since the query, skip
            if contact.last_appointment_status == "scheduled":
                await self._apply_rebooked_tag(contact, db)
                continue
            await self._send_reengagement(
                contact=contact,
                agent=agent,
                template=agent.noshow_day3_template or _DEFAULT_DAY3_TEMPLATE,
                sent_tag="noshow-day3-sent",
                db=db,
            )

        for contact in day7_contacts:
            if contact.last_appointment_status == "scheduled":
                await self._apply_rebooked_tag(contact, db)
                continue
            await self._send_reengagement(
                contact=contact,
                agent=agent,
                template=agent.noshow_day7_template or _DEFAULT_DAY7_TEMPLATE,
                sent_tag="noshow-day7-sent",
                db=db,
            )

    async def _send_reengagement(
        self,
        contact: Contact,
        agent: Agent,
        template: str,
        sent_tag: str,
        db: AsyncSession,
    ) -> None:
        """Send a single re-engagement SMS and tag the contact."""
        log = self.logger.bind(
            contact_id=contact.id,
            agent_id=str(agent.id),
            tag=sent_tag,
        )

        telnyx_key = settings.telnyx_api_key
        if not telnyx_key:
            log.warning("No Telnyx API key configured")
            return

        contact_phone = contact.phone_number
        if not contact_phone:
            log.warning("Contact has no phone number")
            return

        # TCPA compliance — skip opted-out contacts
        is_opted_out = await self.opt_out_manager.check_opt_out(
            contact.workspace_id, contact_phone, db
        )
        if is_opted_out:
            log.info("Skipping noshow re-engagement — contact opted out")
            # Apply the sent tag so we don't retry every hour
            await self._tag_contact(contact, sent_tag, db)
            return

        from_number = await self._resolve_from_number(
            db, contact.id, contact.workspace_id, agent.id
        )
        if not from_number:
            log.warning("Could not resolve from number, will retry next tick")
            return

        latest_noshow_id = await db.scalar(
            select(Appointment.id)
            .where(
                Appointment.workspace_id == contact.workspace_id,
                Appointment.contact_id == contact.id,
                Appointment.status == AppointmentStatus.NO_SHOW,
            )
            .order_by(Appointment.scheduled_at.desc(), Appointment.id.desc())
            .limit(1)
        )
        cause = await db.scalar(
            select(Tag.name)
            .join(ContactTag, ContactTag.tag_id == Tag.id)
            .where(
                Tag.workspace_id == contact.workspace_id,
                ContactTag.contact_id == contact.id,
                Tag.name.in_(tuple(_CAUSE_COPY)),
            )
            .limit(1)
        )
        body = self._render_template(
            template,
            contact,
            agent,
            cause=cause,
            day=3 if sent_tag == "noshow-day3-sent" else 7,
        )

        sms_service = TelnyxSMSService(telnyx_key)
        try:
            idempotency_key = derive_outbound_key(
                "noshow_reengagement",
                agent.id,
                contact.id,
                latest_noshow_id,
                sent_tag,
            )
            message = await sms_service.send_message(
                to_number=contact_phone,
                from_number=from_number,
                body=body,
                db=db,
                workspace_id=contact.workspace_id,
                agent_id=agent.id,
                idempotency_key=idempotency_key,
            )
            log.info("Noshow re-engagement SMS sent", message_id=str(message.id))
            await self._tag_contact(contact, sent_tag, db)
            await db.commit()
        except Exception as exc:
            log.exception("Failed to send noshow re-engagement SMS", error=str(exc))
        finally:
            await sms_service.close()

    async def _apply_rebooked_tag(self, contact: Contact, db: AsyncSession) -> None:
        """Tag a contact as rebooked so we stop all re-engagement sequences."""
        await self._tag_contact(contact, "reengaged-booked", db)
        await db.commit()

    @staticmethod
    async def _tag_contact(contact: Contact, tag: str, db: AsyncSession) -> None:
        """Apply a normalized workspace tag to a contact idempotently."""
        await TagService(db).add_tag_to_contact(
            workspace_id=contact.workspace_id,
            contact_id=contact.id,
            name=tag,
        )

    @staticmethod
    def _has_tag(workspace_id: uuid.UUID, tag_name: str) -> ColumnElement[bool]:
        """Build an EXISTS predicate for one normalized tag."""
        return NoshowReengagementWorker._has_any_tag(workspace_id, [tag_name])

    @staticmethod
    def _has_any_tag(workspace_id: uuid.UUID, tag_names: list[str]) -> ColumnElement[bool]:
        """Build an EXISTS predicate for any normalized tag name."""
        return exists(
            select(ContactTag.id)
            .join(Tag, Tag.id == ContactTag.tag_id)
            .where(
                and_(
                    ContactTag.contact_id == Contact.id,
                    Tag.workspace_id == workspace_id,
                    Tag.name.in_(tag_names),
                )
            )
        )

    def _render_template(
        self,
        template: str,
        contact: Contact,
        agent: Agent,
        cause: str | None = None,
        day: int = 3,
    ) -> str:
        """Render a re-engagement template with placeholders."""
        first_name = contact.first_name or "there"
        reschedule_link = self._build_reschedule_link(contact, agent)

        replacements: dict[str, str] = {
            "first_name": first_name,
            "last_name": contact.last_name or "",
            "reschedule_link": reschedule_link,
            "booking_link": reschedule_link,
            "noshow_cause": cause or "unknown",
            "reengagement_message": _CAUSE_COPY.get(
                cause or "",
                (
                    "we'd still love to connect. Want to reschedule?",
                    "would you like to find another time? Book here:",
                ),
            )[0 if day == 3 else 1],
        }

        message = template
        if cause in _CAUSE_COPY and not re.search(
            r"\{(?:reengagement_message|noshow_cause)\}", template, re.IGNORECASE
        ):
            message = f"{_CAUSE_COPY[cause][0 if day == 3 else 1]} {message}"
        for placeholder, value in replacements.items():
            try:
                pattern = re.compile(rf"\{{{placeholder}\}}", re.IGNORECASE)
                message = pattern.sub(value, message)
            except Exception:
                self.logger.warning(
                    "Placeholder replacement failed",
                    placeholder=placeholder,
                )
        return message

    def _build_reschedule_link(self, contact: Contact, agent: Agent) -> str:
        """Generate a Cal.com booking URL if agent has an event type configured."""
        if not agent.calcom_event_type_id or not settings.calcom_api_key:
            return ""
        try:
            from app.services.calendar.calcom import CalComService

            calcom = CalComService(settings.calcom_api_key)
            contact_name = (
                " ".join(filter(None, [contact.first_name, contact.last_name]))
                or contact.first_name
            )
            return calcom.generate_booking_url(
                event_type_id=agent.calcom_event_type_id,
                contact_email=contact.email or "",
                contact_name=contact_name,
                contact_phone=contact.phone_number,
            )
        except Exception:
            self.logger.warning(
                "Could not generate reschedule link",
                agent_id=str(agent.id),
            )
            return ""

    async def _resolve_from_number(
        self,
        db: AsyncSession,
        contact_id: int,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
    ) -> str | None:
        """Resolve the best from-number for the SMS.

        Strategy 1: Existing conversation with this contact (reuse same number).
        Strategy 2: Agent's assigned phone number.
        Strategy 3: Any active SMS-enabled workspace phone number.
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


# Singleton registry
_registry = WorkerRegistry(NoshowReengagementWorker)
start_noshow_reengagement_worker = _registry.start
stop_noshow_reengagement_worker = _registry.stop
get_noshow_reengagement_worker = _registry.get
