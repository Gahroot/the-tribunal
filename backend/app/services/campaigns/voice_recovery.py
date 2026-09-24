"""Per-contact voice kill switch and durable, bounded campaign recovery.

The existing campaign row is the retry queue. No in-memory timers and no new
campaign enrollment: inbound/manual calls must not acquire marketing consent
or automatic repeat calls merely because a provider failed.
"""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from datetime import time as local_time
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.redis import get_redis
from app.db.session import AsyncSessionLocal
from app.models.campaign import Campaign, CampaignContact, CampaignContactStatus, CampaignStatus
from app.models.conversation import Conversation, Message, MessageDirection
from app.services.campaigns.cadence import MAX_CALL_ATTEMPTS, next_local_slot
from app.services.outbound.delivery import (
    OutboundDeliveryChannel,
    OutboundDeliveryRequest,
    OutboundDeliveryService,
    OutboundDeliveryStatus,
)
from app.services.rate_limiting.opt_out_manager import OptOutManager

logger = structlog.get_logger()
RECOVERY = "provider_failure"
SMS_PENDING = "voice_recovery:sms_pending"
RETRY_SECONDS = 120


def retry_slot(campaign: Campaign, now: datetime) -> datetime:
    """Two minutes, unless sending windows require a later legal slot."""
    earliest = now + timedelta(seconds=RETRY_SECONDS)
    local = earliest.astimezone(ZoneInfo(campaign.timezone or "UTC"))
    if (not campaign.sending_days or local.weekday() in campaign.sending_days) and (
        campaign.sending_hours_start or local_time(9)
    ) <= local.time() <= (campaign.sending_hours_end or local_time(17)):
        return earliest
    return next_local_slot(campaign, earliest)


def _cooldown_key(workspace_id: UUID, provider: str) -> str:
    return f"voice:cooldown:{workspace_id}:{provider}"


async def provider_cooling_down(workspace_id: UUID, provider: str) -> bool:
    """Shared across API/worker replicas; unknown health defers new dials."""
    try:
        async with asyncio.timeout(2):
            redis = await get_redis()
            return bool(await redis.exists(_cooldown_key(workspace_id, provider)))
    except Exception:
        logger.warning("voice_provider_health_unknown", provider=provider)
        return True


async def callback_worker_healthy() -> bool:
    """Use the existing heartbeat, including on API-only deployments."""
    from app.workers.base import HEARTBEAT_TTL_MULTIPLIER, heartbeat_key
    from app.workers.voice_campaign_worker import VoiceCampaignWorker

    try:
        async with asyncio.timeout(2):
            redis = await get_redis()
            raw = await redis.get(heartbeat_key(VoiceCampaignWorker.COMPONENT_NAME))
        age = time.time() - int(raw) if raw is not None else float("inf")
        return 0 <= age <= VoiceCampaignWorker.POLL_INTERVAL_SECONDS * HEARTBEAT_TTL_MULTIPLIER
    except Exception:
        return False


async def notify_recovery(db: AsyncSession, entry: CampaignContact, campaign: Campaign) -> None:
    """Retry notification via the normal delivery gate, never bypass consent."""
    if entry.last_error != SMS_PENDING or entry.opted_out or not entry.contact:
        return
    now = datetime.now(UTC)
    healthy = await callback_worker_healthy()
    soon = bool(entry.next_follow_up_at and entry.next_follow_up_at <= now + timedelta(seconds=125))
    body = (
        "Sorry, our call was interrupted. We'll call you back in 2 minutes. Reply STOP to opt out."
        if healthy and soon
        else "Sorry, our call was interrupted. We'll call you back when service is available "
        "during calling hours. Reply STOP to opt out."
    )
    result = await OutboundDeliveryService().deliver(
        db,
        OutboundDeliveryRequest(
            workspace_id=campaign.workspace_id,
            channel=OutboundDeliveryChannel.SMS,
            to=entry.contact.phone_number,
            from_=campaign.from_phone_number,
            body=body,
            contact=entry.contact,
            campaign=campaign,
            campaign_contact=entry,
            campaign_id=campaign.id,
            agent_id=campaign.voice_agent_id,
            provider_preference="telnyx",
            require_sms_consent=True,
            action_type="voice_provider_recovery",
            idempotency_scope="voice_provider_recovery",
            idempotency_parts=(entry.id, entry.call_message_id),
        ),
    )
    # Telnyx delivery may commit the session. Reacquire the contact lock and
    # refresh the marker before counting a send; a duplicate delivery uses the
    # same idempotency key and must not increment counters twice.
    locked = await db.execute(
        select(CampaignContact)
        .where(CampaignContact.id == entry.id, CampaignContact.campaign_id == campaign.id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    entry = locked.scalar_one()
    if entry.last_error != SMS_PENDING:
        return
    if result.delivered:
        entry.messages_sent += 1
        campaign.messages_sent += 1
        entry.last_error = "voice_recovery:sms_sent"
    elif result.status != OutboundDeliveryStatus.FAILED:
        entry.last_error = "voice_recovery:sms_blocked"
    logger.info("voice_recovery_notification", status=result.status.value, worker_healthy=healthy)


async def recover_voice_call(call_id: str, workspace_id: UUID, provider: str, reason: str) -> bool:
    """Queue once per current attempt before sending SMS or hanging up.

    Locks serialize duplicate bridges and hangup stats. Only the current
    outbound campaign attempt can be requeued, and the normal attempt cap holds.
    """
    try:
        async with asyncio.timeout(2):
            redis = await get_redis()
            await redis.set(_cooldown_key(workspace_id, provider), "1", ex=RETRY_SECONDS)
    except Exception:
        logger.warning("voice_provider_cooldown_write_failed", provider=provider)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CampaignContact)
            .join(Campaign, Campaign.id == CampaignContact.campaign_id)
            .join(Message, Message.id == CampaignContact.call_message_id)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .options(selectinload(CampaignContact.campaign), selectinload(CampaignContact.contact))
            .where(
                Campaign.workspace_id == workspace_id,
                Conversation.workspace_id == workspace_id,
                Message.provider_message_id == call_id,
                Message.direction == MessageDirection.OUTBOUND,
            )
            .with_for_update(of=CampaignContact)
        )
        entry = result.scalar_one_or_none()
        if not entry or entry.status != CampaignContactStatus.CALLING:
            return False
        campaign = entry.campaign
        contact = entry.contact
        if (
            campaign.status != CampaignStatus.RUNNING
            or entry.opted_out
            or not contact
            or contact.workspace_id != workspace_id
            or not contact.phone_number
            or (
                entry.last_reply_at
                and entry.last_call_at
                and entry.last_reply_at >= entry.last_call_at
            )
        ):
            return False
        if await OptOutManager().check_opt_out(workspace_id, contact.phone_number, db):
            entry.opted_out = True
            entry.status = CampaignContactStatus.OPTED_OUT
            entry.next_follow_up_at = None
            await db.commit()
            return False
        entry.last_call_status = RECOVERY
        if entry.call_attempts >= MAX_CALL_ATTEMPTS:
            entry.status = CampaignContactStatus.FAILED
            entry.last_error = "voice_recovery:attempts_exhausted"
            entry.next_follow_up_at = None
            await db.commit()
            return False
        entry.status = CampaignContactStatus.PENDING
        entry.next_follow_up_at = retry_slot(campaign, datetime.now(UTC))
        entry.last_error = SMS_PENDING
        await db.commit()  # SMS failure must never roll back the callback.
        logger.warning(
            "voice_call_requeued", provider=provider, reason=reason, contact_id=entry.contact_id
        )
        try:
            # Re-lock after the durable commit: a worker may have sent the SMS
            # in the meantime. Refresh the marker before touching counters.
            locked = await db.execute(
                select(CampaignContact)
                .where(CampaignContact.id == entry.id)
                .execution_options(populate_existing=True)
                .options(selectinload(CampaignContact.contact))
                .with_for_update()
            )
            entry = locked.scalar_one()
            await notify_recovery(db, entry, campaign)
            await db.commit()
        except Exception:
            logger.exception("voice_recovery_sms_deferred")
        return True
