"""Campaign call stats service.

Updates campaign and campaign_contact stats for ALL call outcomes
(both successful and failed), ensuring calls_answered is always incremented.
"""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.campaign import CampaignContact, CampaignContactStatus
from app.services.campaigns.cadence import (
    approved_best_hour,
    contact_best_hour,
    route_call_outcome,
)


async def update_campaign_call_stats(
    db: AsyncSession,
    message_id: UUID,
    call_outcome: str | None,
    message_status: str,
    duration_secs: int,
    log: structlog.BoundLogger,
    booking_outcome: str | None = None,
) -> None:
    """Update campaign stats for a completed or failed call.

    Args:
        db: Database session
        message_id: ID of the call message
        call_outcome: Classification outcome (None=success, or failure reason)
        message_status: Message status (completed or failed)
        duration_secs: Call duration in seconds
        log: Logger instance
        booking_outcome: Booking outcome (e.g. "success" if appointment booked)
    """
    # Find campaign contact linked to this call
    cc_result = await db.execute(
        select(CampaignContact)
        .options(selectinload(CampaignContact.campaign), selectinload(CampaignContact.contact))
        .where(CampaignContact.call_message_id == message_id)
    )
    campaign_contact = cc_result.scalar_one_or_none()

    if not campaign_contact:
        log.debug("not_a_campaign_call_for_stats", message_id=str(message_id))
        return

    campaign = campaign_contact.campaign
    if not campaign:
        log.warning("missing_campaign_for_stats", message_id=str(message_id))
        return

    # Hangup retries or delayed webhooks for an older attempt must not re-route
    # a contact already queued or actively being called again.
    if campaign_contact.status != CampaignContactStatus.CALLING:
        return

    campaign_contact.call_duration_seconds = duration_secs

    if booking_outcome == "success" or (call_outcome is None and message_status == "completed"):
        # Successful call — real conversation happened
        campaign_contact.last_call_status = "answered"
        route_call_outcome(campaign, campaign_contact, "answered", datetime.now(UTC))
        campaign.calls_answered += 1
        log.info(
            "campaign_call_answered",
            campaign_id=str(campaign.id),
            campaign_contact_id=str(campaign_contact.id),
        )
    elif call_outcome:
        # Failed call
        campaign_contact.last_call_status = call_outcome
        best_hour = await approved_best_hour(db, campaign.workspace_id)
        route_call_outcome(
            campaign,
            campaign_contact,
            call_outcome,
            datetime.now(UTC),
            best_hour=contact_best_hour(campaign, campaign_contact.contact, best_hour),
        )
        if call_outcome == "no_answer":
            campaign.calls_no_answer += 1
        elif call_outcome == "busy":
            campaign.calls_busy += 1
        elif call_outcome == "voicemail":
            campaign.calls_voicemail += 1
        log.info(
            "campaign_call_failed",
            campaign_id=str(campaign.id),
            campaign_contact_id=str(campaign_contact.id),
            outcome=call_outcome,
        )

    if booking_outcome == "success":
        campaign.appointments_booked += 1

    await db.commit()
