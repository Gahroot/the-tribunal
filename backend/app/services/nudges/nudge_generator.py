"""Service for generating human nudges from contact data."""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.human_nudge import HumanNudge
from app.models.opportunity import Opportunity
from app.models.pipeline import PipelineStage
from app.models.workspace import Workspace

logger = logging.getLogger(__name__)

# Default nudge settings
DEFAULT_LEAD_DAYS = 3
DEFAULT_COOLING_DAYS = 30
DEFAULT_DEAL_STALL_DAYS = 7
DEFAULT_HIGH_VALUE_THRESHOLD = 50000
ALL_NUDGE_TYPES = [
    "birthday", "anniversary", "custom", "cooling",
    "follow_up", "deal_milestone", "noshow_recovery",
    "unresponsive", "hot_lead", "referral_ask",
]


class NudgeGeneratorService:
    """Generates HumanNudge rows for upcoming dates and cooling relationships."""

    async def generate_for_workspace(  # noqa: PLR0915
        self, db: AsyncSession, workspace: Workspace
    ) -> int:
        """Generate nudges for all contacts in workspace. Returns count of new nudges."""
        nudge_settings = workspace.settings.get("nudge_settings", {})
        if not isinstance(nudge_settings, dict):
            nudge_settings = {}

        if not nudge_settings.get("enabled", True):
            return 0

        raw_lead = nudge_settings.get("lead_days", DEFAULT_LEAD_DAYS)
        lead_days = int(raw_lead) if raw_lead is not None else DEFAULT_LEAD_DAYS
        raw_cooling = nudge_settings.get("cooling_days", DEFAULT_COOLING_DAYS)
        cooling_days = int(raw_cooling) if raw_cooling is not None else DEFAULT_COOLING_DAYS
        enabled_types: list[str] = nudge_settings.get("nudge_types", ALL_NUDGE_TYPES)

        # Fetch contacts with important_dates set
        result = await db.execute(
            select(Contact).where(
                Contact.workspace_id == workspace.id,
                Contact.important_dates.isnot(None),
            )
        )
        contacts = list(result.scalars().all())

        count = 0

        # Date-based nudges (birthday, anniversary, custom)
        date_types = [t for t in enabled_types if t in ("birthday", "anniversary", "custom")]
        if date_types and contacts:
            count += await self._generate_date_nudges(
                db, workspace.id, contacts, lead_days
            )

        # Cooling nudges
        if "cooling" in enabled_types:
            count += await self._generate_cooling_nudges(
                db, workspace.id, cooling_days
            )

        # Quest: Post-meeting follow-ups
        if "follow_up" in enabled_types:
            count += await self._generate_post_meeting_followups(db, workspace.id)

        # Quest: Deal stage stalls + overdue
        if "deal_milestone" in enabled_types:
            count += await self._generate_deal_stall_nudges(db, workspace.id)
            count += await self._generate_overdue_deal_nudges(db, workspace.id)

        # Quest: Unresponsive leads
        if "unresponsive" in enabled_types:
            count += await self._generate_unresponsive_nudges(db, workspace.id)

        # Quest: No-show recovery
        if "noshow_recovery" in enabled_types:
            count += await self._generate_noshow_recovery_nudges(db, workspace.id)

        # Quest: Hot leads
        if "hot_lead" in enabled_types:
            count += await self._generate_hot_lead_nudges(db, workspace.id)

        # Quest: Referral asks
        if "referral_ask" in enabled_types:
            count += await self._generate_referral_ask_nudges(db, workspace.id)

        if count > 0:
            await db.commit()
            logger.info(
                "Generated %d nudges for workspace %s", count, workspace.id
            )

        return count

    async def _generate_date_nudges(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        contacts: list[Contact],
        lead_days: int,
    ) -> int:
        """Check important_dates and create nudges for upcoming dates."""
        today = datetime.now(UTC).date()
        window_end = today + timedelta(days=lead_days)
        count = 0

        for contact in contacts:
            dates = contact.important_dates
            if not dates:
                continue

            # Check birthday
            birthday_str = dates.get("birthday")
            if birthday_str:
                count += await self._maybe_create_date_nudge(
                    db, workspace_id, contact, "birthday",
                    birthday_str, today, window_end,
                )

            # Check anniversary
            anniversary_str = dates.get("anniversary")
            if anniversary_str:
                count += await self._maybe_create_date_nudge(
                    db, workspace_id, contact, "anniversary",
                    anniversary_str, today, window_end,
                )

            # Check custom dates
            custom_dates: list[dict[str, str]] = dates.get("custom", [])
            for custom in custom_dates:
                label = custom.get("label", "Event")
                date_str = custom.get("date")
                if date_str:
                    count += await self._maybe_create_date_nudge(
                        db, workspace_id, contact, "custom",
                        date_str, today, window_end, label=label,
                    )

        return count

    async def _maybe_create_date_nudge(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        contact: Contact,
        nudge_type: str,
        date_str: str,
        today: date,
        window_end: date,
        label: str | None = None,
    ) -> int:
        """Create a nudge if the date falls within the window. Returns 1 if created."""
        try:
            parsed = datetime.strptime(date_str, "%Y-%m-%d").date()  # noqa: DTZ007
        except (ValueError, TypeError):
            return 0

        # Project the date to this year
        this_year_date = parsed.replace(year=today.year)
        # If the date already passed this year, check next year
        if this_year_date < today:
            this_year_date = parsed.replace(year=today.year + 1)

        if not (today <= this_year_date <= window_end):
            return 0

        days_until: int = (this_year_date - today).days
        dedup_suffix = label or nudge_type
        dedup_key = f"{contact.id}:{dedup_suffix}:{this_year_date.year}"

        # Check idempotency
        existing = await db.execute(
            select(HumanNudge.id).where(HumanNudge.dedup_key == dedup_key).limit(1)
        )
        if existing.scalar_one_or_none() is not None:
            return 0

        title, message, suggested_action = self._build_nudge_message(
            contact, nudge_type,
            date_str=this_year_date.strftime("%B %d"),
            days_until=days_until,
            label=label,
        )

        nudge = HumanNudge(
            workspace_id=workspace_id,
            contact_id=contact.id,
            nudge_type=nudge_type,
            title=title,
            message=message,
            suggested_action=suggested_action,
            priority="high" if days_until <= 1 else "medium",
            due_date=datetime.combine(this_year_date, datetime.min.time(), tzinfo=UTC),
            source_date_field=label or nudge_type,
            status="pending",
            dedup_key=dedup_key,
        )
        db.add(nudge)
        return 1

    async def _generate_cooling_nudges(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        cooling_days: int,
    ) -> int:
        """Create nudges for contacts going cold."""
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=cooling_days)
        year = now.year
        month = now.month

        # Find conversations that have gone cold: have messages but last one
        # is older than cooling_days ago
        result = await db.execute(
            select(Conversation).where(
                Conversation.workspace_id == workspace_id,
                Conversation.last_message_at.isnot(None),
                Conversation.last_message_at < cutoff,
                Conversation.status == "active",
                Conversation.contact_id.isnot(None),
            )
        )
        cold_conversations = result.scalars().all()

        count = 0
        seen_contacts: set[int] = set()

        for conv in cold_conversations:
            contact_id = conv.contact_id
            if contact_id is None or contact_id in seen_contacts:
                continue
            seen_contacts.add(contact_id)

            dedup_key = f"{contact_id}:cooling:{year}:{month}"

            # Check idempotency
            existing = await db.execute(
                select(HumanNudge.id).where(
                    HumanNudge.dedup_key == dedup_key
                ).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                continue

            # Load contact for message building
            contact_result = await db.execute(
                select(Contact).where(Contact.id == contact_id).limit(1)
            )
            contact = contact_result.scalar_one_or_none()
            if contact is None:
                continue

            assert conv.last_message_at is not None  # guarded by isnot(None) filter
            days_silent: int = (now - conv.last_message_at).days

            title, message, suggested_action = self._build_nudge_message(
                contact, "cooling", days_until=days_silent,
            )

            nudge = HumanNudge(
                workspace_id=workspace_id,
                contact_id=contact_id,
                nudge_type="cooling",
                title=title,
                message=message,
                suggested_action=suggested_action,
                priority="low",
                due_date=now,
                source_date_field=None,
                status="pending",
                dedup_key=dedup_key,
            )
            db.add(nudge)
            count += 1

        return count

    async def _generate_post_meeting_followups(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
    ) -> int:
        """Create nudges for contacts after completed meetings without follow-up."""
        now = datetime.now(UTC)
        window_start = now - timedelta(days=7)
        window_end = now - timedelta(days=2)

        result = await db.execute(
            select(Appointment).where(
                Appointment.workspace_id == workspace_id,
                Appointment.status == "completed",
                Appointment.scheduled_at >= window_start,
                Appointment.scheduled_at <= window_end,
            )
        )
        appointments = result.scalars().all()

        count = 0
        for appt in appointments:
            contact_id = appt.contact_id
            dedup_key = f"{contact_id}:post_meeting:{appt.id}"

            existing = await db.execute(
                select(HumanNudge.id).where(
                    HumanNudge.dedup_key == dedup_key
                ).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                continue

            # Check if there's already an outbound message after the appointment
            conv_result = await db.execute(
                select(Conversation).where(
                    Conversation.workspace_id == workspace_id,
                    Conversation.contact_id == contact_id,
                    Conversation.last_message_at > appt.scheduled_at,
                    Conversation.last_message_direction == "outbound",
                ).limit(1)
            )
            if conv_result.scalar_one_or_none() is not None:
                continue

            contact_result = await db.execute(
                select(Contact).where(Contact.id == contact_id).limit(1)
            )
            contact = contact_result.scalar_one_or_none()
            if contact is None:
                continue

            name = contact.full_name
            days_since = (now - appt.scheduled_at).days
            priority = "high" if days_since <= 4 else "medium"

            nudge = HumanNudge(
                workspace_id=workspace_id,
                contact_id=contact_id,
                nudge_type="follow_up",
                title=f"Follow up with {name} after your meeting",
                message=(
                    f"You met with {name} {days_since} days ago. "
                    f"A quick check-in can solidify the relationship."
                ),
                suggested_action="text",
                priority=priority,
                due_date=now,
                source_date_field=None,
                status="pending",
                dedup_key=dedup_key,
            )
            db.add(nudge)
            count += 1

        return count

    async def _generate_deal_stall_nudges(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
    ) -> int:
        """Create nudges for deals stuck in the same stage too long."""
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=DEFAULT_DEAL_STALL_DAYS)
        year = now.year
        week_number = now.isocalendar()[1]

        result = await db.execute(
            select(Opportunity).where(
                Opportunity.workspace_id == workspace_id,
                Opportunity.status == "open",
                Opportunity.stage_changed_at.isnot(None),
                Opportunity.stage_changed_at < cutoff,
            )
        )
        opportunities = result.scalars().all()

        count = 0
        for opp in opportunities:
            if opp.primary_contact_id is None:
                continue

            dedup_key = f"{opp.id}:stalled:{year}:{week_number}"

            existing = await db.execute(
                select(HumanNudge.id).where(
                    HumanNudge.dedup_key == dedup_key
                ).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                continue

            contact_result = await db.execute(
                select(Contact).where(Contact.id == opp.primary_contact_id).limit(1)
            )
            contact = contact_result.scalar_one_or_none()
            if contact is None:
                continue

            # Load stage name
            stage_name = "unknown stage"
            if opp.stage_id is not None:
                stage_result = await db.execute(
                    select(PipelineStage.name).where(
                        PipelineStage.id == opp.stage_id
                    ).limit(1)
                )
                stage_name = stage_result.scalar_one_or_none() or "unknown stage"

            name = contact.full_name
            assert opp.stage_changed_at is not None
            days_stalled = (now - opp.stage_changed_at).days
            amount = float(opp.amount) if opp.amount is not None else 0
            priority = "high" if amount > DEFAULT_HIGH_VALUE_THRESHOLD else "medium"

            nudge = HumanNudge(
                workspace_id=workspace_id,
                contact_id=opp.primary_contact_id,
                nudge_type="deal_milestone",
                title=f"Move {name}'s deal forward",
                message=(
                    f"{name}'s {opp.name} (${amount:,.0f}) has been in "
                    f"{stage_name} for {days_stalled} days."
                ),
                suggested_action="call",
                priority=priority,
                due_date=now,
                source_date_field=None,
                status="pending",
                dedup_key=dedup_key,
            )
            db.add(nudge)
            count += 1

        return count

    async def _generate_overdue_deal_nudges(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
    ) -> int:
        """Create nudges for deals past their expected close date."""
        now = datetime.now(UTC)
        today = now.date()
        year = now.year
        month = now.month

        result = await db.execute(
            select(Opportunity).where(
                Opportunity.workspace_id == workspace_id,
                Opportunity.status == "open",
                Opportunity.expected_close_date.isnot(None),
                Opportunity.expected_close_date < today,
            )
        )
        opportunities = result.scalars().all()

        count = 0
        for opp in opportunities:
            if opp.primary_contact_id is None:
                continue

            dedup_key = f"{opp.id}:overdue:{year}:{month}"

            existing = await db.execute(
                select(HumanNudge.id).where(
                    HumanNudge.dedup_key == dedup_key
                ).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                continue

            contact_result = await db.execute(
                select(Contact).where(Contact.id == opp.primary_contact_id).limit(1)
            )
            contact = contact_result.scalar_one_or_none()
            if contact is None:
                continue

            name = contact.full_name
            assert opp.expected_close_date is not None
            days_overdue = (today - opp.expected_close_date).days

            nudge = HumanNudge(
                workspace_id=workspace_id,
                contact_id=opp.primary_contact_id,
                nudge_type="deal_milestone",
                title=f"\u26a0\ufe0f {name}'s deal is past due",
                message=f"{opp.name} was expected to close {days_overdue} days ago.",
                suggested_action="call",
                priority="high",
                due_date=now,
                source_date_field=None,
                status="pending",
                dedup_key=dedup_key,
            )
            db.add(nudge)
            count += 1

        return count

    async def _generate_unresponsive_nudges(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
    ) -> int:
        """Create nudges for leads that haven't replied to outbound messages."""
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=5)
        year = now.year
        month = now.month

        result = await db.execute(
            select(Conversation).where(
                Conversation.workspace_id == workspace_id,
                Conversation.last_message_at.isnot(None),
                Conversation.last_message_at < cutoff,
                Conversation.last_message_direction == "outbound",
                Conversation.contact_id.isnot(None),
            )
        )
        conversations = result.scalars().all()

        count = 0
        seen_contacts: set[int] = set()

        for conv in conversations:
            contact_id = conv.contact_id
            if contact_id is None or contact_id in seen_contacts:
                continue

            contact_result = await db.execute(
                select(Contact).where(
                    Contact.id == contact_id,
                    Contact.status.in_(["new", "contacted"]),
                ).limit(1)
            )
            contact = contact_result.scalar_one_or_none()
            if contact is None:
                continue

            seen_contacts.add(contact_id)
            dedup_key = f"{contact_id}:unresponsive:{year}:{month}"

            existing = await db.execute(
                select(HumanNudge.id).where(
                    HumanNudge.dedup_key == dedup_key
                ).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                continue

            name = contact.full_name
            assert conv.last_message_at is not None
            days_silent = (now - conv.last_message_at).days

            nudge = HumanNudge(
                workspace_id=workspace_id,
                contact_id=contact_id,
                nudge_type="unresponsive",
                title=f"Re-engage {name}",
                message=(
                    f"{name} hasn't replied in {days_silent} days. "
                    f"Try a different angle or offer."
                ),
                suggested_action="text",
                priority="medium",
                due_date=now,
                source_date_field=None,
                status="pending",
                dedup_key=dedup_key,
            )
            db.add(nudge)
            count += 1

        return count

    async def _generate_noshow_recovery_nudges(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
    ) -> int:
        """Create nudges for contacts who missed appointments recently."""
        now = datetime.now(UTC)
        window_start = now - timedelta(days=3)
        window_end = now - timedelta(days=1)

        result = await db.execute(
            select(Appointment).where(
                Appointment.workspace_id == workspace_id,
                Appointment.status == "no_show",
                Appointment.scheduled_at >= window_start,
                Appointment.scheduled_at <= window_end,
            )
        )
        appointments = result.scalars().all()

        count = 0
        for appt in appointments:
            contact_id = appt.contact_id
            dedup_key = f"{contact_id}:noshow_recovery:{appt.id}"

            existing = await db.execute(
                select(HumanNudge.id).where(
                    HumanNudge.dedup_key == dedup_key
                ).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                continue

            # Check if there's already an outbound message after the no-show
            conv_result = await db.execute(
                select(Conversation).where(
                    Conversation.workspace_id == workspace_id,
                    Conversation.contact_id == contact_id,
                    Conversation.last_message_at > appt.scheduled_at,
                    Conversation.last_message_direction == "outbound",
                ).limit(1)
            )
            if conv_result.scalar_one_or_none() is not None:
                continue

            contact_result = await db.execute(
                select(Contact).where(Contact.id == contact_id).limit(1)
            )
            contact = contact_result.scalar_one_or_none()
            if contact is None:
                continue

            name = contact.full_name
            days_since = (now - appt.scheduled_at).days

            nudge = HumanNudge(
                workspace_id=workspace_id,
                contact_id=contact_id,
                nudge_type="noshow_recovery",
                title=f"Recover no-show with {name}",
                message=(
                    f"{name} missed their appointment {days_since} days ago. "
                    f"A friendly reschedule text works."
                ),
                suggested_action="text",
                priority="high",
                due_date=now,
                source_date_field=None,
                status="pending",
                dedup_key=dedup_key,
            )
            db.add(nudge)
            count += 1

        return count

    async def _generate_hot_lead_nudges(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
    ) -> int:
        """Create nudges for contacts showing high interest signals."""
        now = datetime.now(UTC)
        year = now.year
        quarter = (now.month - 1) // 3 + 1

        result = await db.execute(
            select(Contact).where(
                Contact.workspace_id == workspace_id,
                Contact.qualification_signals.isnot(None),
                Contact.status.notin_(["converted", "lost"]),
            )
        )
        contacts = result.scalars().all()

        count = 0
        for contact in contacts:
            signals = contact.qualification_signals
            if not isinstance(signals, dict):
                continue
            if signals.get("interest_level") != "high":
                continue

            dedup_key = f"{contact.id}:hot_lead:{year}:{quarter}"

            existing = await db.execute(
                select(HumanNudge.id).where(
                    HumanNudge.dedup_key == dedup_key
                ).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                continue

            name = contact.full_name

            nudge = HumanNudge(
                workspace_id=workspace_id,
                contact_id=contact.id,
                nudge_type="hot_lead",
                title=f"\U0001f525 {name} is a hot lead",
                message=(
                    f"{name} shows high interest. "
                    f"Strike while the iron's hot \u2014 book a meeting."
                ),
                suggested_action="call",
                priority="high",
                due_date=now,
                source_date_field=None,
                status="pending",
                dedup_key=dedup_key,
            )
            db.add(nudge)
            count += 1

        return count

    async def _generate_referral_ask_nudges(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
    ) -> int:
        """Create nudges to ask happy clients for referrals."""
        now = datetime.now(UTC)
        year = now.year
        quarter = (now.month - 1) // 3 + 1
        window_start = now - timedelta(days=30)
        window_end = now - timedelta(days=14)

        result = await db.execute(
            select(Appointment).where(
                Appointment.workspace_id == workspace_id,
                Appointment.status == "completed",
                Appointment.scheduled_at >= window_start,
                Appointment.scheduled_at <= window_end,
            )
        )
        appointments = result.scalars().all()

        count = 0
        seen_contacts: set[int] = set()

        for appt in appointments:
            contact_id = appt.contact_id
            if contact_id in seen_contacts:
                continue

            dedup_key = f"{contact_id}:referral_ask:{year}:{quarter}"

            existing = await db.execute(
                select(HumanNudge.id).where(
                    HumanNudge.dedup_key == dedup_key
                ).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                seen_contacts.add(contact_id)
                continue

            contact_result = await db.execute(
                select(Contact).where(Contact.id == contact_id).limit(1)
            )
            contact = contact_result.scalar_one_or_none()
            if contact is None:
                continue

            # Only ask for referrals from converted contacts or those with won deals
            is_happy_client = contact.status == "converted"
            if not is_happy_client:
                won_result = await db.execute(
                    select(Opportunity.id).where(
                        Opportunity.workspace_id == workspace_id,
                        Opportunity.primary_contact_id == contact_id,
                        Opportunity.status == "won",
                    ).limit(1)
                )
                is_happy_client = won_result.scalar_one_or_none() is not None

            if not is_happy_client:
                continue

            seen_contacts.add(contact_id)
            name = contact.full_name
            days_since = (now - appt.scheduled_at).days

            nudge = HumanNudge(
                workspace_id=workspace_id,
                contact_id=contact_id,
                nudge_type="referral_ask",
                title=f"Ask {name} for a referral",
                message=(
                    f"It's been {days_since} days since your meeting with {name}. "
                    f"Happy clients are your best lead source \u2014 ask for a referral."
                ),
                suggested_action="text",
                priority="medium",
                due_date=now,
                source_date_field=None,
                status="pending",
                dedup_key=dedup_key,
            )
            db.add(nudge)
            count += 1

        return count

    def _build_nudge_message(
        self,
        contact: Contact,
        nudge_type: str,
        date_str: str | None = None,
        days_until: int | None = None,
        label: str | None = None,
    ) -> tuple[str, str, str | None]:
        """Returns (title, message, suggested_action) for a nudge type."""
        first = contact.first_name
        last = contact.last_name or ""
        name = f"{first} {last}".strip()

        if nudge_type == "birthday":
            return (
                f"🎂 {name}'s birthday coming up",
                f"🎂 {name}'s birthday is in {days_until} days ({date_str}). "
                f"Consider sending a handwritten card!",
                "send_card",
            )
        elif nudge_type == "anniversary":
            return (
                f"💍 {name}'s anniversary coming up",
                f"💍 {name}'s anniversary is in {days_until} days ({date_str}).",
                "send_card",
            )
        elif nudge_type == "cooling":
            return (
                f"🔄 Re-engage {name}",
                f"🔄 Haven't heard from {name} in {days_until} days. "
                f"Time to reach out?",
                "call",
            )
        else:
            # Custom date
            event_label = label or "Event"
            return (
                f"📅 {event_label} for {name}",
                f"📅 {event_label} for {name} is in {days_until} days ({date_str}).",
                None,
            )


nudge_generator_service = NudgeGeneratorService()
