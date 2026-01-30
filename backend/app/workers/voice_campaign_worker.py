"""Voice campaign worker service for processing voice campaigns with SMS fallback.

This background worker:
1. Polls for running voice campaigns
2. Checks sending hours and rate limits
3. Gets pending contacts and initiates calls
4. Tracks call outcomes via webhook handlers
"""

from datetime import UTC, datetime, time, timedelta
from typing import Any

import pytz
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.campaign import (
    Campaign,
    CampaignContact,
    CampaignContactStatus,
    CampaignStatus,
    CampaignType,
)
from app.services.telephony.telnyx_voice import TelnyxVoiceService
from app.workers.base import BaseWorker, WorkerRegistry

# Worker configuration - more conservative for voice
MAX_CALLS_PER_TICK = 5


class VoiceCampaignWorker(BaseWorker):
    """Background worker for processing voice campaigns."""

    POLL_INTERVAL_SECONDS = 10
    COMPONENT_NAME = "voice_campaign_worker"

    def __init__(self) -> None:
        super().__init__()
        self._rate_trackers: dict[str, list[datetime]] = {}

    async def _process_items(self) -> None:
        """Process all running voice campaigns."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Campaign)
                .options(
                    selectinload(Campaign.voice_agent),
                    selectinload(Campaign.sms_fallback_agent),
                )
                .where(
                    and_(
                        Campaign.status == CampaignStatus.RUNNING.value,
                        Campaign.campaign_type == CampaignType.VOICE_SMS_FALLBACK.value,
                    )
                )
            )
            campaigns = result.scalars().all()

            if not campaigns:
                return

            self.logger.debug("Processing voice campaigns", count=len(campaigns))

            for campaign in campaigns:
                try:
                    await self._process_campaign(campaign, db)
                except Exception:
                    self.logger.exception(
                        "Error processing voice campaign",
                        campaign_id=str(campaign.id),
                        campaign_name=campaign.name,
                    )

    async def _process_campaign(self, campaign: Campaign, db: AsyncSession) -> None:
        """Process a single voice campaign."""
        log = self.logger.bind(
            campaign_id=str(campaign.id),
            campaign_name=campaign.name,
        )

        # Check if within sending hours
        if not self._is_within_sending_hours(campaign):
            log.debug("Outside sending hours")
            return

        # Check if campaign has ended
        if campaign.scheduled_end and datetime.now(UTC) > campaign.scheduled_end:
            log.info("Campaign scheduled end reached, completing")
            campaign.status = CampaignStatus.COMPLETED.value
            campaign.completed_at = datetime.now(UTC)
            await db.commit()
            return

        # Get voice service
        if not settings.telnyx_api_key:
            log.warning("No Telnyx API key configured")
            return

        voice_service = TelnyxVoiceService(settings.telnyx_api_key)
        try:
            # Process pending calls
            await self._process_pending_calls(campaign, voice_service, db, log)

            # Check if campaign is complete
            await self._check_completion(campaign, db, log)

            await db.commit()
        finally:
            await voice_service.close()

    async def _process_pending_calls(
        self,
        campaign: Campaign,
        voice_service: TelnyxVoiceService,
        db: AsyncSession,
        log: Any,
    ) -> None:
        """Initiate calls to pending contacts."""
        available_slots = self._get_available_call_slots(campaign)
        if available_slots <= 0:
            log.debug("Rate limit reached for this minute")
            return

        calls_to_make = min(available_slots, MAX_CALLS_PER_TICK)

        # Get pending contacts with row-level locking
        pending_result = await db.execute(
            select(CampaignContact)
            .options(selectinload(CampaignContact.contact))
            .where(
                and_(
                    CampaignContact.campaign_id == campaign.id,
                    CampaignContact.status == CampaignContactStatus.PENDING.value,
                    CampaignContact.opted_out.is_(False),
                )
            )
            .order_by(
                CampaignContact.priority.desc(),
                CampaignContact.created_at,
            )
            .limit(calls_to_make)
            .with_for_update(skip_locked=True)
        )
        pending_contacts = pending_result.scalars().all()

        if not pending_contacts:
            return

        log.info(
            "Initiating calls",
            count=len(pending_contacts),
            available_slots=available_slots,
        )

        # Build webhook URL
        api_base = settings.api_base_url or "http://localhost:8000"
        webhook_url = f"{api_base}/webhooks/telnyx/voice"

        # Get connection ID from settings or campaign (None = auto-discover)
        connection_id = campaign.voice_connection_id or settings.telnyx_connection_id

        for campaign_contact in pending_contacts:
            contact = campaign_contact.contact
            if not contact or not contact.phone_number:
                log.warning(
                    "Contact missing phone number",
                    contact_id=campaign_contact.contact_id,
                )
                campaign_contact.status = CampaignContactStatus.FAILED.value
                campaign_contact.last_error = "missing_phone_number"
                continue

            try:
                # Initiate call
                message = await voice_service.initiate_call(
                    to_number=contact.phone_number,
                    from_number=campaign.from_phone_number,
                    connection_id=connection_id,
                    webhook_url=webhook_url,
                    db=db,
                    workspace_id=campaign.workspace_id,
                    contact_phone=contact.phone_number,
                    agent_id=campaign.voice_agent_id,
                    enable_machine_detection=campaign.enable_machine_detection,
                    campaign_id=campaign.id,
                )

                # Update campaign contact
                campaign_contact.status = CampaignContactStatus.CALLING.value
                campaign_contact.call_attempts += 1
                campaign_contact.last_call_at = datetime.now(UTC)
                campaign_contact.call_message_id = message.id

                # Update campaign stats
                campaign.calls_attempted += 1

                # Track rate limiting
                self._track_call_made(str(campaign.id))

                log.info(
                    "Call initiated",
                    contact_id=contact.id,
                    phone=contact.phone_number,
                    message_id=str(message.id),
                    call_attempt=campaign_contact.call_attempts,
                )

            except Exception as e:
                log.exception(
                    "Failed to initiate call",
                    contact_id=contact.id,
                    phone=contact.phone_number,
                    error=str(e),
                )
                campaign_contact.status = CampaignContactStatus.FAILED.value
                campaign_contact.last_error = str(e)
                campaign.error_count += 1
                campaign.last_error = str(e)
                campaign.last_error_at = datetime.now(UTC)

    async def _check_completion(
        self,
        campaign: Campaign,
        db: AsyncSession,
        log: Any,
    ) -> None:
        """Check if campaign is complete."""
        # Count contacts still pending or being called
        remaining_result = await db.execute(
            select(func.count(CampaignContact.id)).where(
                and_(
                    CampaignContact.campaign_id == campaign.id,
                    CampaignContact.status.in_([
                        CampaignContactStatus.PENDING.value,
                        CampaignContactStatus.CALLING.value,
                    ]),
                )
            )
        )
        remaining = remaining_result.scalar() or 0

        if remaining == 0:
            log.info("All contacts processed, completing campaign")
            campaign.status = CampaignStatus.COMPLETED.value
            campaign.completed_at = datetime.now(UTC)

    def _is_within_sending_hours(self, campaign: Campaign) -> bool:
        """Check if current time is within campaign sending hours."""
        # Use 'is None' instead of falsy check since time(0, 0) is falsy in Python
        if campaign.sending_hours_start is None or campaign.sending_hours_end is None:
            self.logger.debug(
                "Sending hours not set, allowing",
                start=campaign.sending_hours_start,
                end=campaign.sending_hours_end,
            )
            return True

        tz = pytz.timezone(campaign.timezone or "UTC")
        now = datetime.now(tz)

        # Only check sending_days if it's a non-empty list
        if campaign.sending_days and now.weekday() not in campaign.sending_days:
            self.logger.debug(
                "Not a sending day",
                sending_days=campaign.sending_days,
                weekday=now.weekday(),
            )
            return False

        # Handle both time objects and datetime objects from SQLAlchemy Time column
        start_val = campaign.sending_hours_start
        end_val = campaign.sending_hours_end
        start_time: time = start_val.time() if isinstance(start_val, datetime) else start_val
        end_time: time = end_val.time() if isinstance(end_val, datetime) else end_val
        current_time = now.time()

        result = start_time <= current_time <= end_time
        self.logger.debug(
            "Sending hours check",
            start_time=str(start_time),
            end_time=str(end_time),
            current_time=str(current_time),
            result=result,
        )
        return result

    def _get_available_call_slots(self, campaign: Campaign) -> int:
        """Calculate how many calls can be made based on rate limit."""
        campaign_id = str(campaign.id)
        now = datetime.now(UTC)
        cutoff = now - timedelta(minutes=1)

        if campaign_id in self._rate_trackers:
            self._rate_trackers[campaign_id] = [
                call_time
                for call_time in self._rate_trackers[campaign_id]
                if call_time > cutoff
            ]
            calls_in_last_minute = len(self._rate_trackers[campaign_id])
        else:
            calls_in_last_minute = 0

        return max(0, campaign.calls_per_minute - calls_in_last_minute)

    def _track_call_made(self, campaign_id: str) -> None:
        """Track a call for rate limiting."""
        if campaign_id not in self._rate_trackers:
            self._rate_trackers[campaign_id] = []
        self._rate_trackers[campaign_id].append(datetime.now(UTC))


# Singleton registry
_registry = WorkerRegistry(VoiceCampaignWorker)
start_voice_campaign_worker = _registry.start
stop_voice_campaign_worker = _registry.stop
get_voice_campaign_worker = _registry.get
