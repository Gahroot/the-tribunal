"""Setup prerequisites — the owned checklist The Tribunal must satisfy to run.

Before The Tribunal can autonomously run a workspace's sales floor it needs a
small, fixed set of prerequisites in place: a saved ad monitor feeding leads, an
active offer to sell, outbound autopilot turned on, and an SMS/iMessage-capable
sending number. These were previously surfaced only as passive "setup gap" cards
on the Today queue.

This module turns them into a single, evaluable checklist so two consumers share
one source of truth:

* :class:`~app.services.dashboard.today_queue_service.TodayQueueService` renders
  the unmet prerequisites as ``setup_gap`` cards, and
* :class:`~app.services.reporting.operator_report_service.OperatorReportService`
  actively chases the operator over iMessage about the unmet ones — re-chasing
  until each is resolved, without repeating a prerequisite that is already done.

Each prerequisite carries the specific two-minute fix so the chase message can
tell the operator exactly what to do, not just that something is missing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.offer import Offer
from app.models.outbound_mission import OutboundMission
from app.models.phone_number import PhoneNumber
from app.models.workspace import Workspace
from app.services.ad_intelligence.monitors import AD_MONITOR_KEY, is_active_monitor
from app.services.autonomy_mandate import normalize_autonomy_mandate
from app.services.telephony.availability import (
    TELEPHONY_SETUP_ACTION_HREF,
    TELEPHONY_UNAVAILABLE_MESSAGE,
    is_telephony_enabled_for_workspace,
)


@dataclass(slots=True, frozen=True)
class SetupPrerequisite:
    """One prerequisite The Tribunal needs satisfied to run the floor.

    ``key`` is the stable checklist slot (``monitor``/``offer``/``autopilot``/
    ``delivery``); ``gap`` is the rendered card identifier, which for the
    delivery slot varies between ``phone`` and ``telephony`` depending on whether
    Telnyx is connected. ``short_title`` and ``fix`` power the iMessage chase.
    """

    key: str
    gap: str
    met: bool
    short_title: str
    title: str
    body: str
    fix: str
    cta_label: str
    href: str


@dataclass(slots=True, frozen=True)
class SetupPrerequisiteReport:
    """Evaluated prerequisite checklist for a workspace."""

    prerequisites: tuple[SetupPrerequisite, ...]

    @property
    def total(self) -> int:
        return len(self.prerequisites)

    @property
    def met(self) -> tuple[SetupPrerequisite, ...]:
        return tuple(p for p in self.prerequisites if p.met)

    @property
    def unmet(self) -> tuple[SetupPrerequisite, ...]:
        return tuple(p for p in self.prerequisites if not p.met)

    @property
    def met_count(self) -> int:
        return len(self.met)

    @property
    def all_met(self) -> bool:
        return not self.unmet

    @property
    def unmet_signature(self) -> str:
        """Stable identity of the current unmet set, for chase de-duplication."""
        return ",".join(p.gap for p in self.unmet)


class SetupPrerequisiteService:
    """Evaluates the fixed setup-prerequisite checklist for a workspace."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def evaluate(self, workspace_id: uuid.UUID) -> SetupPrerequisiteReport:
        """Return the prerequisite checklist in stable display order."""
        prerequisites = (
            await self._monitor_prerequisite(workspace_id),
            await self._offer_prerequisite(workspace_id),
            await self._autopilot_prerequisite(workspace_id),
            await self._delivery_prerequisite(workspace_id),
        )
        return SetupPrerequisiteReport(prerequisites=prerequisites)

    # ── individual prerequisites ──────────────────────────────────────

    async def _monitor_prerequisite(self, workspace_id: uuid.UUID) -> SetupPrerequisite:
        met = await self._has_active_monitor(workspace_id)
        return SetupPrerequisite(
            key="monitor",
            gap="monitor",
            met=met,
            short_title="an active ad monitor",
            title="The scraper is off — set an ad monitor",
            body=(
                "No active ad-library monitor. Save a recurring search so fresh "
                "advertisers land in your queue every morning."
            ),
            fix="Open Find Leads → Ad Library and save a recurring search.",
            cta_label="Set up a monitor",
            href="/find-leads/ad-library",
        )

    async def _offer_prerequisite(self, workspace_id: uuid.UUID) -> SetupPrerequisite:
        result = await self.db.execute(
            select(Offer.id)
            .where(Offer.workspace_id == workspace_id, Offer.is_active.is_(True))
            .limit(1)
        )
        met = result.scalar_one_or_none() is not None
        return SetupPrerequisite(
            key="offer",
            gap="offer",
            met=met,
            short_title="an active offer",
            title="No active offer",
            body="Outbound campaigns need an offer to promote. Create or activate one.",
            fix="Open Offers and activate the Batch Video Ads offer.",
            cta_label="Create an offer",
            href="/offers",
        )

    async def _autopilot_prerequisite(self, workspace_id: uuid.UUID) -> SetupPrerequisite:
        met = await self._autopilot_enabled(workspace_id)
        return SetupPrerequisite(
            key="autopilot",
            gap="autopilot",
            met=met,
            short_title="outbound autopilot",
            title="Outbound autopilot is off",
            body=(
                "Fresh ad-library contacts won't become a drafted campaign "
                "overnight. Turn on autopilot and pick a default offer."
            ),
            fix="Open Settings → Lead Sources and turn on outbound autopilot.",
            cta_label="Turn on autopilot",
            href="/settings?tab=lead-sources",
        )

    async def _delivery_prerequisite(self, workspace_id: uuid.UUID) -> SetupPrerequisite:
        sms_number = await self.db.execute(
            select(PhoneNumber.id)
            .where(
                PhoneNumber.workspace_id == workspace_id,
                PhoneNumber.is_active.is_(True),
                PhoneNumber.sms_enabled.is_(True),
            )
            .limit(1)
        )
        if sms_number.scalar_one_or_none() is not None:
            return SetupPrerequisite(
                key="delivery",
                gap="phone",
                met=True,
                short_title="an SMS/iMessage number",
                title="No SMS-enabled phone number",
                body="You need an active SMS-enabled number before any campaign can send.",
                fix="Open Phone Numbers and activate an SMS/iMessage-enabled number.",
                cta_label="Add a number",
                href="/phone-numbers",
            )

        if await is_telephony_enabled_for_workspace(self.db, workspace_id):
            return SetupPrerequisite(
                key="delivery",
                gap="phone",
                met=False,
                short_title="an SMS/iMessage number",
                title="No SMS-enabled phone number",
                body="You need an active SMS-enabled number before any campaign can send.",
                fix="Open Phone Numbers and activate an SMS/iMessage-enabled number.",
                cta_label="Add a number",
                href="/phone-numbers",
            )

        return SetupPrerequisite(
            key="delivery",
            gap="telephony",
            met=False,
            short_title="telephony",
            title="Telephony is not connected",
            body=TELEPHONY_UNAVAILABLE_MESSAGE,
            fix="Open Settings → Integrations and connect Telnyx.",
            cta_label="Connect Telnyx",
            href=TELEPHONY_SETUP_ACTION_HREF,
        )

    # ── shared checks ─────────────────────────────────────────────────

    async def _autopilot_enabled(self, workspace_id: uuid.UUID) -> bool:
        result = await self.db.execute(
            select(Workspace.autonomy_mandate).where(Workspace.id == workspace_id)
        )
        mandate = normalize_autonomy_mandate(result.scalar_one_or_none())
        return bool(mandate.get("enabled") and mandate.get("auto_send_first_touches"))

    async def _has_active_monitor(self, workspace_id: uuid.UUID) -> bool:
        result = await self.db.execute(
            select(OutboundMission).where(
                OutboundMission.workspace_id == workspace_id,
                OutboundMission.discovery_config[AD_MONITOR_KEY].isnot(None),
            )
        )
        return any(is_active_monitor(m) for m in result.scalars().all())
