"""Pre-launch recipient eligibility for SMS campaigns.

Previews and launches reuse :class:`OutboundComplianceService` — the same
rules the campaign worker applies right before each send — so a preview can
explain why recipients will be withheld without ever bypassing a safeguard.
The worker still re-evaluates every recipient at send time; nothing computed
here authorises a send.

Recipients fall into three buckets:

* **eligible** — passes every recipient-level rule right now;
* **excluded** — withheld by a recipient-level rule (opt-out, no SMS consent,
  no phone number, duplicate, per-contact cap) until the operator changes
  something about that contact;
* **already contacted** — rows past their initial send (resume/relaunch).

Timing rules (sending window, quiet hours, campaign send cap) are reported once
per campaign as a *deferral*: they delay sends, they never exclude anyone.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.campaign import (
    Campaign,
    CampaignContact,
    CampaignContactStatus,
    CampaignType,
)
from app.models.contact import Contact
from app.models.phone_number import PhoneNumber
from app.services.campaigns.sending_window import is_within_sending_window
from app.services.compliance.outbound_compliance import (
    RECIPIENT_EXCLUSION_REASONS,
    OutboundComplianceRequest,
    OutboundComplianceResult,
    OutboundComplianceService,
)

# Max contact ids returned per exclusion reason (enough to drive a recovery
# action such as recording consent; counts are always exact).
MAX_CONTACT_IDS_PER_REASON = 1000

CONTACT_NOT_FOUND = "contact_not_found"
MISSING_PHONE_NUMBER = "missing_phone_number"
MISSING_SMS_CONSENT = "missing_sms_consent"
GLOBAL_OPT_OUT = "global_opt_out"

EXCLUSION_LABELS: dict[str, str] = {
    GLOBAL_OPT_OUT: "Opted out of texts",
    MISSING_SMS_CONSENT: "No SMS consent on file",
    MISSING_PHONE_NUMBER: "No phone number",
    "duplicate_campaign_contact": "Already messaged in this campaign",
    "contact_send_cap_reached": "Per-contact message limit reached",
    CONTACT_NOT_FOUND: "Not found in this workspace",
}

DEFERRAL_LABELS: dict[str, str] = {
    "outside_sending_window": "Outside the campaign's sending days/hours",
    "quiet_hours": "Inside the campaign's quiet hours",
    "campaign_send_cap_reached": "Campaign send limit reached",
}

# Statuses whose rows are (re)evaluated before launch. Everything else has
# already moved past its initial send (or was opted out by the contact).
_EVALUATED_STATUSES = (CampaignContactStatus.PENDING, CampaignContactStatus.EXCLUDED)


def exclusion_label(reason: str) -> str:
    """Human-readable label for an exclusion reason."""
    return EXCLUSION_LABELS.get(reason, reason.replace("_", " ").capitalize())


@dataclass(slots=True)
class RecipientExclusion:
    """One exclusion reason with its recipient count."""

    reason: str
    count: int
    contact_ids: list[int]

    @property
    def label(self) -> str:
        return exclusion_label(self.reason)

    @property
    def recoverable_with_consent(self) -> bool:
        return self.reason == MISSING_SMS_CONSENT


@dataclass(slots=True)
class RecipientEligibility:
    """Eligibility summary for a campaign audience at a point in time."""

    channel: str
    consent_required: bool
    checked_at: datetime
    selected_count: int = 0
    eligible_count: int = 0
    already_contacted_count: int = 0
    exclusions: list[RecipientExclusion] = field(default_factory=list)
    deferral_reason: str | None = None
    deferral_details: dict[str, object] = field(default_factory=dict)
    # Persisted campaigns only: evaluated rows and their verdicts by row id.
    rows: list[CampaignContact] = field(default_factory=list, repr=False)
    verdicts: dict[uuid.UUID, OutboundComplianceResult] = field(default_factory=dict, repr=False)

    @property
    def excluded_count(self) -> int:
        return sum(exclusion.count for exclusion in self.exclusions)

    @property
    def ready_to_send(self) -> bool:
        return self.eligible_count > 0

    @property
    def deferral_label(self) -> str | None:
        if self.deferral_reason is None:
            return None
        return DEFERRAL_LABELS.get(self.deferral_reason, self.deferral_reason)

    def exclusion_summary(self) -> str:
        """Short ``"2 no SMS consent on file, 1 opted out"`` style summary."""
        return ", ".join(
            f"{exclusion.count} {exclusion.label.lower()}" for exclusion in self.exclusions
        )


def _channel_for_sender(sender: PhoneNumber | None) -> str:
    # Mirrors campaign_worker._campaign_channel_for_phone. An unknown sender is
    # treated as SMS, the stricter channel (consent required).
    if sender is not None and sender.imessage_enabled:
        return "imessage"
    return "sms"


async def resolve_campaign_sender(
    db: AsyncSession, workspace_id: uuid.UUID, from_phone_number: str
) -> PhoneNumber | None:
    """Return the workspace's phone number row for a campaign sender."""
    result = await db.execute(
        select(PhoneNumber).where(
            PhoneNumber.workspace_id == workspace_id,
            PhoneNumber.phone_number == from_phone_number,
        )
    )
    return result.scalar_one_or_none()


class RecipientEligibilityService:
    """Evaluate SMS campaign recipients with the authoritative compliance rules."""

    def __init__(self, compliance_service: OutboundComplianceService | None = None) -> None:
        self.compliance_service = compliance_service or OutboundComplianceService()

    async def preview_contacts(
        self,
        db: AsyncSession,
        *,
        campaign: Campaign,
        contact_ids: Sequence[int],
        sender: PhoneNumber | None,
        now: datetime | None = None,
    ) -> RecipientEligibility:
        """Preview a not-yet-created campaign for a selection of contact ids.

        ``campaign`` is a transient (never added to the session) campaign
        carrying the draft's schedule; contacts are scoped to its workspace.
        """
        checked_at = now or datetime.now(UTC)
        channel = _channel_for_sender(sender)
        summary = RecipientEligibility(
            channel=channel, consent_required=channel == "sms", checked_at=checked_at
        )
        unique_ids = list(dict.fromkeys(contact_ids))
        summary.selected_count = len(unique_ids)

        contacts_result = await db.execute(
            select(Contact).where(
                Contact.workspace_id == campaign.workspace_id,
                Contact.id.in_(unique_ids),
            )
        )
        contacts = {contact.id: contact for contact in contacts_result.scalars().all()}
        opted_out = await self.compliance_service.opt_out_manager.opted_out_numbers(
            campaign.workspace_id,
            (contact.phone_number for contact in contacts.values()),
            db,
        )

        reasons: dict[str, list[int]] = {}
        for contact_id in unique_ids:
            contact = contacts.get(contact_id)
            if contact is None:
                reasons.setdefault(CONTACT_NOT_FOUND, []).append(contact_id)
                continue
            verdict = await self._evaluate(
                db, campaign, None, contact, channel, checked_at, opted_out
            )
            self._tally(summary, reasons, contact_id, verdict)

        self._finish(summary, reasons, campaign, checked_at)
        return summary

    async def evaluate_campaign(
        self,
        db: AsyncSession,
        campaign: Campaign,
        *,
        now: datetime | None = None,
    ) -> RecipientEligibility:
        """Evaluate every recipient of a persisted campaign (read-only)."""
        checked_at = now or datetime.now(UTC)
        sender = await resolve_campaign_sender(
            db, campaign.workspace_id, campaign.from_phone_number
        )
        channel = _channel_for_sender(sender)
        summary = RecipientEligibility(
            channel=channel, consent_required=channel == "sms", checked_at=checked_at
        )

        rows_result = await db.execute(
            select(CampaignContact)
            .options(selectinload(CampaignContact.contact))
            .where(CampaignContact.campaign_id == campaign.id)
        )
        rows = list(rows_result.scalars().all())
        summary.rows = rows
        summary.selected_count = len(rows)

        evaluated = [row for row in rows if row.status in _EVALUATED_STATUSES]
        opted_out = await self.compliance_service.opt_out_manager.opted_out_numbers(
            campaign.workspace_id,
            (row.contact.phone_number for row in evaluated if row.contact is not None),
            db,
        )

        reasons: dict[str, list[int]] = {}
        for row in rows:
            if row.status not in _EVALUATED_STATUSES:
                if row.status == CampaignContactStatus.OPTED_OUT and row.messages_sent == 0:
                    reasons.setdefault(GLOBAL_OPT_OUT, []).append(row.contact_id)
                else:
                    summary.already_contacted_count += 1
                continue
            verdict = await self._evaluate(
                db, campaign, row, row.contact, channel, checked_at, opted_out
            )
            summary.verdicts[row.id] = verdict
            self._tally(summary, reasons, row.contact_id, verdict)

        self._finish(summary, reasons, campaign, checked_at)
        return summary

    def apply_to_campaign(self, campaign: Campaign, summary: RecipientEligibility) -> None:
        """Persist launch-time verdicts onto campaign contacts.

        Excluded rows leave the send queue with their reason recorded (so the
        worker never spins on them); previously excluded rows that now pass
        return to PENDING. The worker still rechecks each PENDING row at send.
        """
        for row in summary.rows:
            verdict = summary.verdicts.get(row.id)
            if verdict is None:
                continue
            if verdict.allowed:
                if row.status == CampaignContactStatus.EXCLUDED:
                    row.status = CampaignContactStatus.PENDING
                # Clears any stale exclusion/deferral reason on the row.
                self.compliance_service.apply_suppression(row, verdict, summary.checked_at)
            elif verdict.reason in RECIPIENT_EXCLUSION_REASONS:
                self.compliance_service.apply_suppression(row, verdict, summary.checked_at)
                if verdict.reason == GLOBAL_OPT_OUT:
                    # apply_suppression already marked the row OPTED_OUT.
                    campaign.contacts_opted_out += 1
                else:
                    row.status = CampaignContactStatus.EXCLUDED

    async def _evaluate(
        self,
        db: AsyncSession,
        campaign: Campaign,
        campaign_contact: CampaignContact | None,
        contact: Contact | None,
        channel: str,
        now: datetime,
        opted_out: frozenset[str],
    ) -> OutboundComplianceResult:
        if contact is None or not contact.phone_number:
            return OutboundComplianceResult(allowed=False, reason=MISSING_PHONE_NUMBER)
        return await self.compliance_service.evaluate(
            OutboundComplianceRequest(
                workspace_id=campaign.workspace_id,
                campaign=campaign,
                campaign_contact=campaign_contact,
                contact=contact,
                channel=channel,
                action_type=f"campaign_initial_{channel}",
                now=now,
                include_campaign_gates=False,
                known_opted_out_numbers=opted_out,
            ),
            db,
        )

    @staticmethod
    def _tally(
        summary: RecipientEligibility,
        reasons: dict[str, list[int]],
        contact_id: int,
        verdict: OutboundComplianceResult,
    ) -> None:
        # Campaign-wide gates are evaluated once in ``_finish``; every verdict
        # here is recipient-level.
        if verdict.allowed:
            summary.eligible_count += 1
        else:
            reasons.setdefault(verdict.reason or "blocked", []).append(contact_id)

    def _finish(
        self,
        summary: RecipientEligibility,
        reasons: dict[str, list[int]],
        campaign: Campaign,
        now: datetime,
    ) -> None:
        counts = Counter({reason: len(ids) for reason, ids in reasons.items()})
        summary.exclusions = [
            RecipientExclusion(
                reason=reason,
                count=count,
                contact_ids=reasons[reason][:MAX_CONTACT_IDS_PER_REASON],
            )
            for reason, count in counts.most_common()
        ]
        if not is_within_sending_window(campaign, now):
            summary.deferral_reason = "outside_sending_window"
            return
        quiet = self.compliance_service.quiet_hours_details(campaign, now)
        if quiet is not None:
            summary.deferral_reason = "quiet_hours"
            summary.deferral_details = quiet
            return
        cap = self.compliance_service.campaign_send_cap_details(campaign)
        if cap is not None:
            summary.deferral_reason = "campaign_send_cap_reached"
            summary.deferral_details = cap


def build_draft_campaign(
    *,
    workspace_id: uuid.UUID,
    from_phone_number: str,
    sending_hours_start: time | None,
    sending_hours_end: time | None,
    sending_days: list[int] | None,
    timezone: str,
) -> Campaign:
    """Build a transient campaign for previewing a not-yet-created SMS campaign.

    Every attribute the compliance rules read is set explicitly because ORM
    column defaults only apply on INSERT. The object is never added to a session.
    """
    return Campaign(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        campaign_type=CampaignType.SMS,
        name="preview",
        from_phone_number=from_phone_number,
        sending_hours_start=sending_hours_start,
        sending_hours_end=sending_hours_end,
        sending_days=sending_days,
        timezone=timezone,
        quiet_hours_start=None,
        quiet_hours_end=None,
        quiet_hours_timezone=None,
        messages_sent=0,
        max_messages_per_campaign=None,
        max_messages_per_contact=5,
    )


_SENT_STATUSES = frozenset(
    {
        CampaignContactStatus.SENT,
        CampaignContactStatus.DELIVERED,
        CampaignContactStatus.REPLIED,
        CampaignContactStatus.QUALIFIED,
        CampaignContactStatus.COMPLETED,
    }
)


@dataclass(slots=True)
class RecipientBreakdown:
    """Initial-message progress per recipient: sent vs deferred vs excluded."""

    sent: int = 0
    queued: int = 0
    deferred: int = 0
    excluded: int = 0
    opted_out: int = 0
    failed: int = 0
    excluded_reasons: dict[str, int] = field(default_factory=dict)
    deferred_reasons: dict[str, int] = field(default_factory=dict)


async def campaign_recipient_breakdown(
    db: AsyncSession, campaign_id: uuid.UUID
) -> RecipientBreakdown:
    """Count campaign recipients by initial-message outcome (one grouped query)."""
    result = await db.execute(
        select(
            CampaignContact.status,
            CampaignContact.suppressed_reason,
            CampaignContact.first_sent_at.is_not(None),
            func.count(),
        )
        .where(CampaignContact.campaign_id == campaign_id)
        .group_by(
            CampaignContact.status,
            CampaignContact.suppressed_reason,
            CampaignContact.first_sent_at.is_not(None),
        )
    )
    breakdown = RecipientBreakdown()
    for raw_status, reason, was_sent, count in result.all():
        row_status = CampaignContactStatus(raw_status)
        if was_sent or row_status in _SENT_STATUSES:
            breakdown.sent += count
        elif row_status == CampaignContactStatus.EXCLUDED:
            breakdown.excluded += count
            key = reason or "excluded"
            breakdown.excluded_reasons[key] = breakdown.excluded_reasons.get(key, 0) + count
        elif row_status == CampaignContactStatus.OPTED_OUT:
            breakdown.opted_out += count
        elif row_status == CampaignContactStatus.FAILED:
            breakdown.failed += count
        elif row_status == CampaignContactStatus.PENDING and reason:
            # Still queued but last attempt was held by a timing/capacity rule.
            breakdown.deferred += count
            breakdown.deferred_reasons[reason] = breakdown.deferred_reasons.get(reason, 0) + count
        else:
            breakdown.queued += count
    return breakdown
