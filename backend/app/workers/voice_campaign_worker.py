"""Voice campaign worker service for processing voice campaigns with SMS fallback.

This background worker:
1. Polls for running voice campaigns
2. Checks sending hours and rate limits
3. Gets pending contacts and initiates calls
4. Tracks call outcomes via webhook handlers
"""

from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import QueryableAttribute, selectinload

from app.core.config import settings
from app.models.campaign import (
    Campaign,
    CampaignContact,
    CampaignContactStatus,
    CampaignType,
)
from app.models.contact import Contact
from app.services.campaigns.cadence import (
    MAX_CALL_ATTEMPTS,
    approved_best_hour,
    contact_best_hour,
    next_local_slot,
    route_call_outcome,
    sms_touch_due_at,
    sms_touch_pending,
)
from app.services.campaigns.voice_experiments import assign_voice
from app.services.campaigns.voice_recovery import (
    RECOVERY,
    SMS_PENDING,
    notify_recovery,
    provider_cooling_down,
    retry_slot,
)
from app.services.idempotency import derive_outbound_key
from app.services.rate_limiting.opt_out_manager import OptOutManager
from app.services.telephony.telnyx_voice import TelnyxVoiceService
from app.workers.base import WorkerRegistry
from app.workers.base_campaign_worker import BaseCampaignWorker

# Worker configuration - more conservative for voice
MAX_CALLS_PER_TICK = 5


class VoiceCampaignWorker(BaseCampaignWorker):
    """Background worker for processing voice campaigns."""

    POLL_INTERVAL_SECONDS = 10
    COMPONENT_NAME = "voice_campaign_worker"
    # Voice calls are expensive and rate-limited per phone number; stay
    # conservative — MAX_CALLS_PER_TICK gates the upper bound anyway.
    MAX_CONCURRENCY = 5
    max_retries = 3
    backoff_base_seconds = 2.0

    def __init__(self) -> None:
        super().__init__()
        self._rate_trackers: dict[str, list[datetime]] = {}

    @property
    def campaign_type(self) -> CampaignType:
        return CampaignType.VOICE_SMS_FALLBACK

    @property
    def eager_loads(self) -> list[QueryableAttribute[Any]]:
        return [Campaign.voice_agent, Campaign.sms_fallback_agent]

    def _is_within_sending_hours(self, campaign: Campaign) -> bool:
        """Never dial outside the local daytime window, even on a late tick."""
        now = datetime.now(ZoneInfo(campaign.timezone or "UTC"))
        if campaign.sending_days and now.weekday() not in campaign.sending_days:
            return False
        start = campaign.sending_hours_start or time(9)
        end = campaign.sending_hours_end or time(17)
        return start <= now.time() <= end

    def _get_remaining_filter(self, campaign: Campaign) -> Any:
        return and_(
            CampaignContact.campaign_id == campaign.id,
            CampaignContact.status.in_(
                [
                    CampaignContactStatus.PENDING,
                    CampaignContactStatus.CALLING,
                    CampaignContactStatus.SMS_FALLBACK_SENT,
                ]
            ),
        )

    async def _process_campaign_contacts(
        self,
        campaign: Campaign,
        db: AsyncSession,
        log: Any,
    ) -> None:
        """Process voice campaign contacts: clean up stuck calls and initiate new ones."""
        voice_service = TelnyxVoiceService(settings.telnyx_api_key)
        try:
            await self._requeue_terminal_attempts(campaign, db)
            await self._cleanup_stuck_calls(campaign, db, log)
            await self._process_recovery_sms(campaign, db)
            await self._process_scheduled_sms(campaign, db, log)
            await self._process_pending_calls(campaign, voice_service, db, log)
            await self._check_completion(campaign, db, log)
            await db.commit()
        finally:
            await voice_service.close()

    async def _process_recovery_sms(self, campaign: Campaign, db: AsyncSession) -> None:
        result = await db.execute(
            select(CampaignContact)
            .options(selectinload(CampaignContact.contact))
            .where(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.status == CampaignContactStatus.PENDING,
                CampaignContact.last_error == SMS_PENDING,
                CampaignContact.opted_out.is_(False),
            )
            .limit(MAX_CALLS_PER_TICK)
            .with_for_update(skip_locked=True)
        )
        for entry in result.scalars():
            await notify_recovery(db, entry, campaign)

    async def _process_scheduled_sms(self, campaign: Campaign, db: AsyncSession, log: Any) -> None:
        """Send due SMS between calls, bounded by the campaign message caps."""
        if not campaign.sms_fallback_enabled or not settings.telnyx_api_key:
            return
        if not campaign.sms_fallback_template and not (
            campaign.sms_fallback_use_ai and campaign.sms_fallback_agent_id
        ):
            return
        from app.services.campaigns.sms_fallback import send_sms_fallback

        sms_limit = campaign.max_messages_per_contact
        if sms_limit is None:
            sms_limit = 5
        result = await db.execute(
            select(CampaignContact)
            .options(selectinload(CampaignContact.contact))
            .where(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.status.in_(
                    (CampaignContactStatus.PENDING, CampaignContactStatus.SMS_FALLBACK_SENT)
                ),
                CampaignContact.call_attempts.in_((1, 3, 5)),
                CampaignContact.last_call_status.in_(("no_answer", "busy", "voicemail")),
                CampaignContact.last_call_at <= datetime.now(UTC) - timedelta(hours=2),
                or_(
                    CampaignContact.sms_fallback_sent_at.is_(None),
                    CampaignContact.sms_fallback_sent_at < CampaignContact.last_call_at,
                ),
                CampaignContact.opted_out.is_(False),
                CampaignContact.messages_sent < sms_limit,
                or_(
                    CampaignContact.last_reply_at.is_(None),
                    CampaignContact.last_reply_at < CampaignContact.last_call_at,
                ),
                CampaignContact.contact.has(Contact.phone_number.is_not(None)),
            )
            .order_by(CampaignContact.last_call_at)
            .limit(MAX_CALLS_PER_TICK)
            .with_for_update(skip_locked=True)
        )
        best_hour = await approved_best_hour(db, campaign.workspace_id)
        for entry in result.scalars():
            if not sms_touch_pending(campaign, entry):
                continue
            outcome = entry.last_call_status
            if outcome is None:
                continue
            if sms_touch_due_at(campaign, entry) > datetime.now(UTC):
                continue
            if not entry.contact or not entry.contact.phone_number:
                continue
            sent = await send_sms_fallback(
                db,
                campaign,
                entry,
                entry.contact,
                outcome,
                settings.telnyx_api_key,
            )
            if not sent:
                # A refused or failed delivery does not retry every ten seconds.
                # The next eligible call can try a new, separately keyed touch.
                entry.sms_fallback_sent_at = datetime.now(UTC)
                log.info("scheduled_sms_skipped", campaign_contact_id=str(entry.id))
            if entry.next_follow_up_at:
                earliest = datetime.now(UTC) + timedelta(hours=2)
                if entry.next_follow_up_at < earliest:
                    entry.next_follow_up_at = next_local_slot(
                        campaign,
                        earliest,
                        hour=contact_best_hour(campaign, entry.contact, best_hour),
                    )

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

        provider = campaign.voice_agent.voice_provider if campaign.voice_agent else "openai"
        if await provider_cooling_down(campaign.workspace_id, provider):
            log.warning("voice_campaign_provider_cooling_down", provider=provider)
            return

        # Get pending contacts with row-level locking
        pending_result = await db.execute(
            select(CampaignContact)
            .options(selectinload(CampaignContact.contact))
            .where(
                and_(
                    CampaignContact.campaign_id == campaign.id,
                    CampaignContact.status.in_(
                        (CampaignContactStatus.PENDING, CampaignContactStatus.SMS_FALLBACK_SENT)
                    ),
                    or_(
                        CampaignContact.next_follow_up_at.is_(None),
                        CampaignContact.next_follow_up_at <= datetime.now(UTC),
                    ),
                    CampaignContact.call_attempts < MAX_CALL_ATTEMPTS,
                    CampaignContact.opted_out.is_(False),
                )
            )
            .order_by(
                CampaignContact.priority.desc(),
                CampaignContact.next_follow_up_at.asc().nulls_first(),
                CampaignContact.created_at,
            )
            .limit(min(available_slots, MAX_CALLS_PER_TICK))
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

        best_hour = await approved_best_hour(db, campaign.workspace_id)
        for campaign_contact in pending_contacts:
            contact = campaign_contact.contact
            if not contact or not contact.phone_number:
                log.warning(
                    "Contact missing phone number",
                    contact_id=campaign_contact.contact_id,
                )
                campaign_contact.status = CampaignContactStatus.FAILED
                campaign_contact.last_error = "missing_phone_number"
                continue

            if not await self._recovery_allows_call(campaign, campaign_contact, contact, db):
                continue

            local_best_hour = contact_best_hour(campaign, contact, best_hour)
            if self._defer_call_for_sms(campaign, campaign_contact, local_best_hour):
                continue
            if campaign_contact.call_attempts == 0 and campaign_contact.next_follow_up_at is None:
                due = next_local_slot(campaign, datetime.now(UTC), hour=local_best_hour)
                if due > datetime.now(UTC):
                    campaign_contact.next_follow_up_at = due
                    continue

            try:
                # Stable per-(campaign_contact, attempt) key so a crash
                # between the Message row insert and Telnyx /calls POST
                # doesn't double-dial. ``call_attempts`` here is the
                # 0-indexed next attempt (it's incremented after success).
                idempotency_key = derive_outbound_key(
                    "voice_campaign_call",
                    campaign_contact.id,
                    campaign_contact.call_attempts,
                )

                # Persist the assignment in the same transaction as the call's
                # Message. Deterministic assignment also survives a rolled-back dial.
                assign_voice(campaign, campaign_contact)

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
                    idempotency_key=idempotency_key,
                )

                if not self._record_started_call(campaign, campaign_contact, message):
                    log.warning("voice_campaign_dial_failed", reason=campaign_contact.last_error)
                    break

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
                campaign_contact.status = CampaignContactStatus.FAILED
                campaign_contact.last_error = str(e)
                campaign.error_count += 1
                campaign.last_error = str(e)
                campaign.last_error_at = datetime.now(UTC)

    @staticmethod
    def _record_started_call(campaign: Campaign, entry: CampaignContact, message: Any) -> bool:
        if getattr(message, "error_code", None) == "RATE_LIMITED":
            entry.next_follow_up_at = retry_slot(campaign, datetime.now(UTC))
            entry.last_error = "voice_recovery:rate_limited"
            return False
        if getattr(message, "status", None) == "failed":
            entry.status = CampaignContactStatus.FAILED
            entry.last_error = "voice_recovery:dial_failed"
            return False
        entry.status = CampaignContactStatus.CALLING
        entry.last_call_status = None
        entry.last_error = None
        entry.call_attempts += 1
        entry.last_call_at = datetime.now(UTC)
        entry.first_sent_at = entry.first_sent_at or entry.last_call_at
        entry.next_follow_up_at = None
        entry.call_message_id = message.id
        campaign.calls_attempted += 1
        return True

    @staticmethod
    async def _recovery_allows_call(
        campaign: Campaign, entry: CampaignContact, contact: Contact, db: AsyncSession
    ) -> bool:
        if entry.last_call_status != RECOVERY:
            return True
        if not contact.phone_number:
            return False
        if await OptOutManager().check_opt_out(campaign.workspace_id, contact.phone_number, db):
            entry.opted_out = True
            entry.status = CampaignContactStatus.OPTED_OUT
            entry.next_follow_up_at = None
            return False
        if entry.last_reply_at and entry.last_call_at and entry.last_reply_at >= entry.last_call_at:
            entry.status = CampaignContactStatus.COMPLETED
            entry.next_follow_up_at = None
            return False
        return True

    def _defer_call_for_sms(
        self, campaign: Campaign, entry: CampaignContact, best_hour: int | None
    ) -> bool:
        if entry.last_call_status == RECOVERY:
            return False  # Recovery SMS is not a two-hour marketing cadence touch.
        if settings.telnyx_api_key and sms_touch_pending(campaign, entry):
            # The SMS slot comes before the next call, even when overdue.
            return True
        if (
            entry.sms_fallback_sent_at
            and entry.last_call_at
            and entry.sms_fallback_sent_at >= entry.last_call_at
        ):
            earliest = entry.sms_fallback_sent_at + timedelta(hours=2)
            if datetime.now(UTC) < earliest and (
                entry.next_follow_up_at is None or entry.next_follow_up_at < earliest
            ):
                entry.next_follow_up_at = next_local_slot(campaign, earliest, hour=best_hour)
                return True
        return False

    async def _requeue_terminal_attempts(self, campaign: Campaign, db: AsyncSession) -> None:
        """Recover failed outcomes left terminal by workers deployed before cadence."""
        result = await db.execute(
            select(CampaignContact)
            .options(selectinload(CampaignContact.contact))
            .where(
                CampaignContact.campaign_id == campaign.id,
                or_(
                    CampaignContact.status == CampaignContactStatus.CALL_FAILED,
                    and_(
                        CampaignContact.status == CampaignContactStatus.SMS_FALLBACK_SENT,
                        or_(
                            CampaignContact.next_follow_up_at.is_(None),
                            CampaignContact.call_attempts >= MAX_CALL_ATTEMPTS,
                        ),
                    ),
                    and_(
                        CampaignContact.status == CampaignContactStatus.PENDING,
                        CampaignContact.call_attempts >= MAX_CALL_ATTEMPTS,
                    ),
                ),
                CampaignContact.opted_out.is_(False),
            )
            .order_by(CampaignContact.last_call_at)
            .limit(100)
            .with_for_update(skip_locked=True)
        )
        contacts = result.scalars().all()
        if not contacts:
            return
        best_hour = await approved_best_hour(db, campaign.workspace_id)
        for contact in contacts:
            route_call_outcome(
                campaign,
                contact,
                contact.last_call_status or "no_answer",
                contact.last_call_at or datetime.now(UTC),
                best_hour=contact_best_hour(campaign, contact.contact, best_hour),
            )

    async def _cleanup_stuck_calls(
        self,
        campaign: Campaign,
        db: AsyncSession,
        log: Any,
    ) -> None:
        """Clean up contacts stuck in 'calling' status when webhooks never arrive.

        If a contact has been in 'calling' status for more than 5 minutes,
        route it as no-answer through the bounded retry ladder.
        """
        stuck_timeout = timedelta(minutes=5)
        cutoff_time = datetime.now(UTC) - stuck_timeout

        # Find contacts stuck in calling status
        stuck_result = await db.execute(
            select(CampaignContact)
            .options(selectinload(CampaignContact.contact))
            .where(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.status == CampaignContactStatus.CALLING,
                CampaignContact.last_call_at < cutoff_time,
            )
            .limit(100)
            .with_for_update(skip_locked=True)
        )
        stuck_contacts = stuck_result.scalars().all()

        if not stuck_contacts:
            return

        log.warning(
            "cleaning_up_stuck_calls",
            count=len(stuck_contacts),
            timeout_minutes=5,
        )

        best_hour = await approved_best_hour(db, campaign.workspace_id)
        for contact in stuck_contacts:
            outcome = "voicemail" if contact.last_call_status == "voicemail" else "no_answer"
            contact.last_call_status = outcome
            route_call_outcome(
                campaign,
                contact,
                outcome,
                datetime.now(UTC),
                best_hour=contact_best_hour(campaign, contact.contact, best_hour),
            )
            contact.last_error = "Call webhook timeout - no response after 5 minutes"
            campaign.calls_no_answer += 1

        log.info("stuck_calls_cleaned_up", count=len(stuck_contacts))

    def _get_available_call_slots(self, campaign: Campaign) -> int:
        """Calculate how many calls can be made based on rate limit."""
        campaign_id = str(campaign.id)
        now = datetime.now(UTC)
        cutoff = now - timedelta(minutes=1)

        if campaign_id in self._rate_trackers:
            self._rate_trackers[campaign_id] = [
                call_time for call_time in self._rate_trackers[campaign_id] if call_time > cutoff
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
