"""Shared campaign lifecycle transitions for API, assistant tools, and workers."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignContact, CampaignStatus, CampaignType
from app.services.campaigns.recipient_eligibility import (
    RecipientEligibility,
    RecipientEligibilityService,
)
from app.services.campaigns.sending_window import as_utc, has_scheduled_start_arrived


class CampaignLifecycleError(Exception):
    """Raised when a campaign lifecycle transition is not allowed."""


@dataclass(frozen=True, slots=True)
class CampaignLifecycleResult:
    """Result of a campaign lifecycle transition."""

    status: CampaignStatus
    message: str
    contact_count: int | None = None
    # SMS campaigns only: launch-time recipient eligibility (rechecked here,
    # and again by the worker at send time).
    eligibility: RecipientEligibility | None = None


class CampaignNotSendableError(CampaignLifecycleError):
    """Raised when an SMS campaign has no recipient who may currently be messaged."""

    def __init__(self, message: str, eligibility: RecipientEligibility) -> None:
        super().__init__(message)
        self.eligibility = eligibility


def _is_sms_campaign(campaign: Campaign) -> bool:
    return campaign.campaign_type in (CampaignType.SMS, CampaignType.SMS.value)


def _eligibility_message(prefix: str, eligibility: RecipientEligibility) -> str:
    message = (
        f"{prefix}: {eligibility.eligible_count} of {eligibility.selected_count} "
        "recipients eligible now"
    )
    if eligibility.exclusions:
        message += f"; {eligibility.excluded_count} excluded ({eligibility.exclusion_summary()})"
    if eligibility.deferral_label:
        message += f". Sends deferred: {eligibility.deferral_label.lower()}"
    return message


async def _recheck_sms_recipients(
    db: AsyncSession,
    campaign: Campaign,
    eligibility_service: RecipientEligibilityService | None,
    *,
    require_eligible: bool,
) -> RecipientEligibility:
    """Re-evaluate recipients with the send-time rules and persist the verdicts.

    Never trusts an earlier preview. When ``require_eligible`` and nobody can be
    messaged (and nobody was messaged before), nothing is persisted and
    :class:`CampaignNotSendableError` is raised so the campaign is not reported
    as delivering.
    """
    service = eligibility_service or RecipientEligibilityService()
    eligibility = await service.evaluate_campaign(db, campaign)
    if (
        require_eligible
        and eligibility.eligible_count == 0
        and eligibility.already_contacted_count == 0
    ):
        detail = eligibility.exclusion_summary() or "no recipients"
        raise CampaignNotSendableError(
            "No recipients can be messaged yet "
            f"({detail}). Record SMS consent for these contacts or choose a "
            "different audience, then start again.",
            eligibility,
        )
    service.apply_to_campaign(campaign, eligibility)
    return eligibility


async def get_campaign_for_workspace(
    db: AsyncSession,
    campaign_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> Campaign | None:
    """Return a campaign scoped to a workspace."""
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.workspace_id == workspace_id,
        )
    )
    return result.scalar_one_or_none()


async def count_campaign_contacts(db: AsyncSession, campaign_id: uuid.UUID) -> int:
    """Count contacts enrolled in a campaign."""
    count_result = await db.execute(
        select(func.count(CampaignContact.id)).where(CampaignContact.campaign_id == campaign_id)
    )
    return count_result.scalar() or 0


async def start_campaign(
    db: AsyncSession,
    campaign: Campaign,
    contact_count: int | None = None,
    eligibility_service: RecipientEligibilityService | None = None,
) -> CampaignLifecycleResult:
    """Start a draft, paused, or scheduled campaign with worker-compatible status.

    SMS campaigns recheck recipient eligibility with the authoritative
    compliance rules and refuse to start when nobody may be messaged.
    """
    if campaign.status not in {
        CampaignStatus.DRAFT,
        CampaignStatus.PAUSED,
        CampaignStatus.SCHEDULED,
    }:
        raise CampaignLifecycleError(f"Cannot start campaign with status: {campaign.status}")

    enrolled_count = (
        await count_campaign_contacts(db, campaign.id) if contact_count is None else contact_count
    )
    if enrolled_count == 0:
        raise CampaignLifecycleError("Campaign has no contacts")

    eligibility: RecipientEligibility | None = None
    message = f"Campaign started with {enrolled_count} contacts"
    if _is_sms_campaign(campaign):
        eligibility = await _recheck_sms_recipients(
            db, campaign, eligibility_service, require_eligible=True
        )
        message = _eligibility_message("Campaign started", eligibility)

    if not has_scheduled_start_arrived(campaign):
        assert campaign.scheduled_start is not None
        message = (
            f"Campaign scheduled; no sends before {as_utc(campaign.scheduled_start).isoformat()}. "
            "Sending days/hours and recipient safeguards still apply. "
            + message.replace("Campaign started", "Campaign armed")
        )

    campaign.status = CampaignStatus.RUNNING
    campaign.started_at = datetime.now(UTC)
    if campaign.guarantee_target and campaign.guarantee_target > 0:
        campaign.guarantee_status = "pending"

    return CampaignLifecycleResult(
        status=CampaignStatus.RUNNING,
        message=message,
        contact_count=enrolled_count,
        eligibility=eligibility,
    )


async def pause_campaign(campaign: Campaign) -> CampaignLifecycleResult:
    """Pause a running campaign."""
    if campaign.status != CampaignStatus.RUNNING:
        raise CampaignLifecycleError("Can only pause running campaigns")

    campaign.status = CampaignStatus.PAUSED
    return CampaignLifecycleResult(status=CampaignStatus.PAUSED, message="Campaign paused")


async def resume_campaign(
    db: AsyncSession,
    campaign: Campaign,
    contact_count: int | None = None,
    eligibility_service: RecipientEligibilityService | None = None,
) -> CampaignLifecycleResult:
    """Resume a paused campaign with worker-compatible status.

    SMS campaigns re-evaluate excluded recipients so consent recorded while
    paused returns them to the queue. Resume never refuses on eligibility
    because already-contacted recipients may still have follow-ups due.
    """
    if campaign.status != CampaignStatus.PAUSED:
        raise CampaignLifecycleError("Can only resume paused campaigns")

    enrolled_count = (
        await count_campaign_contacts(db, campaign.id) if contact_count is None else contact_count
    )
    if enrolled_count == 0:
        raise CampaignLifecycleError("Campaign has no contacts")

    eligibility: RecipientEligibility | None = None
    message = "Campaign resumed"
    if _is_sms_campaign(campaign):
        eligibility = await _recheck_sms_recipients(
            db, campaign, eligibility_service, require_eligible=False
        )
        message = _eligibility_message("Campaign resumed", eligibility)

    if not has_scheduled_start_arrived(campaign):
        assert campaign.scheduled_start is not None
        message = (
            f"Campaign scheduled; no sends before {as_utc(campaign.scheduled_start).isoformat()}. "
            "Sending days/hours and recipient safeguards still apply. "
            + message.replace("Campaign resumed", "Campaign armed")
        )

    campaign.status = CampaignStatus.RUNNING
    return CampaignLifecycleResult(
        status=CampaignStatus.RUNNING,
        message=message,
        contact_count=enrolled_count,
        eligibility=eligibility,
    )


def summarize_campaign(campaign: Campaign) -> dict[str, Any]:
    """Return campaign summary metrics and calculated rates."""
    reply_rate = (
        campaign.replies_received / campaign.messages_sent if campaign.messages_sent > 0 else 0.0
    )
    delivery_rate = (
        campaign.messages_delivered / campaign.messages_sent if campaign.messages_sent > 0 else 0.0
    )
    qualification_rate = (
        campaign.contacts_qualified / campaign.total_contacts
        if campaign.total_contacts > 0
        else 0.0
    )

    return {
        "id": str(campaign.id),
        "name": campaign.name,
        "status": (
            campaign.status.value
            if isinstance(campaign.status, CampaignStatus)
            else campaign.status
        ),
        "type": campaign.campaign_type,
        "total_contacts": campaign.total_contacts,
        "messages_sent": campaign.messages_sent,
        "messages_delivered": campaign.messages_delivered,
        "messages_failed": campaign.messages_failed,
        "replies_received": campaign.replies_received,
        "contacts_qualified": campaign.contacts_qualified,
        "contacts_opted_out": campaign.contacts_opted_out,
        "appointments_booked": campaign.appointments_booked,
        "appointments_completed": campaign.appointments_completed,
        "calls_attempted": campaign.calls_attempted,
        "calls_answered": campaign.calls_answered,
        "sms_fallbacks_sent": campaign.sms_fallbacks_sent,
        "guarantee_target": campaign.guarantee_target,
        "guarantee_status": campaign.guarantee_status,
        "started_at": campaign.started_at.isoformat() if campaign.started_at else None,
        "completed_at": campaign.completed_at.isoformat() if campaign.completed_at else None,
        "rates": {
            "reply_rate": reply_rate,
            "delivery_rate": delivery_rate,
            "qualification_rate": qualification_rate,
        },
    }
