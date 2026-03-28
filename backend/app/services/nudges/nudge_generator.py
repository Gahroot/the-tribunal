"""Service for generating human nudges from contact data."""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.human_nudge import HumanNudge
from app.models.workspace import Workspace

logger = logging.getLogger(__name__)

# Default nudge settings
DEFAULT_LEAD_DAYS = 3
DEFAULT_COOLING_DAYS = 30
ALL_NUDGE_TYPES = ["birthday", "anniversary", "custom", "cooling"]


class NudgeGeneratorService:
    """Generates HumanNudge rows for upcoming dates and cooling relationships."""

    async def generate_for_workspace(
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
