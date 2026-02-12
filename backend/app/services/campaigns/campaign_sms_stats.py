"""Campaign SMS stats service.

Updates campaign and campaign_contact stats for SMS reply and delivery events.
"""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.campaign import CampaignContact


async def update_campaign_sms_reply(
    db: AsyncSession,
    conversation_id: UUID,
    log: structlog.BoundLogger,
) -> None:
    """Update campaign stats when a contact replies to an SMS.

    Args:
        db: Database session
        conversation_id: Conversation ID from the inbound message
        log: Logger instance
    """
    cc_result = await db.execute(
        select(CampaignContact)
        .options(selectinload(CampaignContact.campaign))
        .where(CampaignContact.conversation_id == conversation_id)
    )
    campaign_contact = cc_result.scalar_one_or_none()

    if not campaign_contact:
        log.debug("not_a_campaign_reply", conversation_id=str(conversation_id))
        return

    campaign = campaign_contact.campaign
    if not campaign:
        log.warning("missing_campaign_for_sms_reply", conversation_id=str(conversation_id))
        return

    campaign.replies_received += 1
    campaign_contact.status = "replied"
    campaign_contact.messages_received += 1
    campaign_contact.last_reply_at = datetime.now(UTC)

    await db.commit()
    log.info(
        "campaign_sms_reply_recorded",
        campaign_id=str(campaign.id),
        campaign_contact_id=str(campaign_contact.id),
    )


async def update_campaign_sms_delivery(
    db: AsyncSession,
    conversation_id: UUID,
    delivered: bool,
    log: structlog.BoundLogger,
) -> None:
    """Update campaign stats for SMS delivery or failure.

    Args:
        db: Database session
        conversation_id: Conversation ID from the delivery status update
        delivered: True if delivered, False if failed
        log: Logger instance
    """
    cc_result = await db.execute(
        select(CampaignContact)
        .options(selectinload(CampaignContact.campaign))
        .where(CampaignContact.conversation_id == conversation_id)
    )
    campaign_contact = cc_result.scalar_one_or_none()

    if not campaign_contact:
        log.debug("not_a_campaign_delivery", conversation_id=str(conversation_id))
        return

    campaign = campaign_contact.campaign
    if not campaign:
        log.warning("missing_campaign_for_sms_delivery", conversation_id=str(conversation_id))
        return

    if delivered:
        campaign.messages_delivered += 1
        if campaign_contact.status == "sent":
            campaign_contact.status = "delivered"
        log.info(
            "campaign_sms_delivered",
            campaign_id=str(campaign.id),
            campaign_contact_id=str(campaign_contact.id),
        )
    else:
        campaign.messages_failed += 1
        log.info(
            "campaign_sms_failed",
            campaign_id=str(campaign.id),
            campaign_contact_id=str(campaign_contact.id),
        )

    await db.commit()
