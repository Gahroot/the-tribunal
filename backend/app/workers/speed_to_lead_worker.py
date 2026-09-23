"""Instant speed-to-lead first touch: voice attempt + "we're calling you now" SMS.

Lead-creation hooks (public lead forms, the landing demo, offers, the embed
widget) push a job onto ``speed_to_lead:queue`` the moment a new lead commits.
This worker drains the queue on a fast poll so the first touch lands well
inside the 5-minute speed-to-lead window (leads reached within 5 minutes are
dramatically more likely to qualify):

* an outbound voice attempt via :class:`TelnyxVoiceService`, fired
* in parallel with a "we're calling you now" SMS through the unified
  outbound delivery service.

Both channels run through the shared outbound compliance gates in
``app.services.compliance.outbound_compliance`` — global opt-out, consent
policy, and quiet hours — before anything is dialled or sent. Quiet-hours
blocks are rescheduled to the next quiet-hours end (up to ``MAX_DEFERRALS``)
instead of dropped; contact-level opt-outs are audited and dropped. Every
gate decision writes an ``OutboundActionAuditLog`` row, and both sends are
idempotent per (workspace, contact) so replays and retries never double-dial
or double-text.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable
from datetime import UTC, datetime, time, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.redis import get_redis
from app.db.session import AsyncSessionLocal
from app.models.agent import Agent
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.outbound_action_audit_log import OutboundActionAuditLog
from app.models.phone_number import PhoneNumber
from app.models.workspace import Workspace
from app.services.autonomy_mandate import normalize_autonomy_mandate
from app.services.compliance.outbound_compliance import (
    OutboundComplianceRequest,
    OutboundComplianceResult,
    OutboundComplianceService,
)
from app.services.idempotency import derive_outbound_key, derive_worker_retry_key
from app.services.outbound.delivery import (
    OutboundDeliveryChannel,
    OutboundDeliveryRequest,
    OutboundDeliveryStatus,
    outbound_delivery_service,
)
from app.services.sla.speed_to_lead import (
    CHANNEL_SMS,
    CHANNEL_VOICE,
    DELAYED_QUEUE_KEY,
    QUEUE_KEY,
    get_speed_to_lead_settings,
    normalize_first_touch_channels,
)
from app.services.telephony.telnyx_voice import TelnyxVoiceService
from app.workers.base import BaseWorker, WorkerRegistry
from app.workers.retryable import RetryableWorker

# Compliance/audit action types, one per channel.
_VOICE_ACTION = "speed_to_lead.voice_dial"
_SMS_ACTION = "speed_to_lead.first_touch_sms"

# Audit source tag for every row this worker writes.
_AUDIT_SOURCE = "speed_to_lead_worker"

# Deterministic idempotency scope so a (workspace, contact) pair is dialled at
# most once and texted at most once, no matter how often a job is replayed.
_DIAL_IDEMPOTENCY_SCOPE = "speed_to_lead_dial"
_SMS_IDEMPOTENCY_SCOPE = "speed_to_lead_sms"


class SpeedToLeadWorker(RetryableWorker, BaseWorker):
    """Drain the instant first-touch queue and fire voice + SMS in parallel."""

    POLL_INTERVAL_SECONDS = settings.speed_to_lead_poll_interval
    COMPONENT_NAME = "speed_to_lead_worker"
    # Each job opens up to three DB sessions (gate + two parallel sends), so
    # keep the per-cycle concurrency modest to stay inside the pool.
    MAX_CONCURRENCY = 4
    # Small batches: every job is real telephony, so stay well under any
    # per-second provider burst limits.
    BATCH_SIZE = 8
    # Quiet-hours deferrals before the job gives up. Each deferral is roughly
    # a day, so three covers a long weekend without ever hot-looping.
    MAX_DEFERRALS = 3

    def __init__(self) -> None:
        super().__init__()
        self.compliance = OutboundComplianceService()
        # Jobs currently inside ``execute_with_retry`` for the same
        # (workspace, contact). Guards the tiny window where a duplicate job
        # could interleave with an in-flight dial whose Message row has not
        # committed yet (idempotency covers everything after commit).
        self._inflight_jobs: set[str] = set()

    # -------------------------------------------------------------------------
    # Queue plumbing
    # -------------------------------------------------------------------------

    async def _process_items(self) -> None:
        """Promote deferred jobs, drain the queue, and process each job."""
        await self._promote_delayed_jobs()
        jobs = await self._drain_jobs()
        if not jobs:
            return
        results = await self.run_concurrently([self._run_one(job) for job in jobs])
        for outcome in results:
            if isinstance(outcome, BaseException):
                self.logger.warning("speed_to_lead_job_error", error=str(outcome))
        self.record_items_processed(len(jobs))

    async def _run_one(self, job: dict[str, Any]) -> None:
        """Process one job under retry, deduping same-key jobs in flight."""
        item_key = derive_worker_retry_key(
            "speed_to_lead",
            str(job.get("workspace_id", "?")),
            str(job.get("contact_id", "?")),
        )
        if item_key in self._inflight_jobs:
            self.logger.info("speed_to_lead_duplicate_job", item_key=item_key)
            return
        self._inflight_jobs.add(item_key)
        try:
            await self.execute_with_retry(self._process_job, job, item_key=item_key)
        finally:
            self._inflight_jobs.discard(item_key)

    async def _drain_jobs(self) -> list[dict[str, Any]]:
        """Pop up to ``BATCH_SIZE`` jobs off the queue, tolerating bad rows."""
        try:
            client = await get_redis()
            # ``cast`` absorbs redis-py's sync/async return-union under mypy strict.
            pop = cast(
                Awaitable[list[str] | str | None],
                client.lpop(QUEUE_KEY, self.BATCH_SIZE),
            )
            raw = await pop
        except Exception:
            self.logger.exception("speed_to_lead_drain_failed")
            return []
        if not raw:
            return []
        items = raw if isinstance(raw, list) else [raw]
        jobs: list[dict[str, Any]] = []
        for item in items:
            try:
                payload = json.loads(item)
            except (TypeError, ValueError):
                self.logger.warning("speed_to_lead_bad_job")
                continue
            if isinstance(payload, dict):
                jobs.append(payload)
            else:
                self.logger.warning("speed_to_lead_bad_job")
        return jobs

    async def _promote_delayed_jobs(self) -> None:
        """Move quiet-hours-deferred jobs whose run time arrived back on-queue."""
        try:
            client = await get_redis()
            due = await client.zrangebyscore(
                DELAYED_QUEUE_KEY,
                0,
                datetime.now(UTC).timestamp(),
                start=0,
                num=self.BATCH_SIZE,
            )
        except Exception:
            self.logger.exception("speed_to_lead_delayed_scan_failed")
            return
        for payload in due:
            remove = cast(Awaitable[int], client.zrem(DELAYED_QUEUE_KEY, payload))
            if await remove:
                push = cast(Awaitable[int], client.rpush(QUEUE_KEY, payload))
                await push

    # -------------------------------------------------------------------------
    # Job pipeline
    # -------------------------------------------------------------------------

    async def _process_job(self, job: dict[str, Any]) -> None:
        """Run one queued lead: gates -> compliance -> parallel sends -> audit."""
        channels = normalize_first_touch_channels(job.get("channels"))
        if not channels:
            return
        try:
            workspace_id = uuid.UUID(str(job["workspace_id"]))
            contact_id = int(job["contact_id"])
        except (KeyError, TypeError, ValueError):
            self.logger.warning("speed_to_lead_bad_job", job_keys=sorted(job))
            return
        attempts = _as_int(job.get("attempts"))

        async with AsyncSessionLocal() as db:
            workspace = await db.get(Workspace, workspace_id)
            contact = await db.get(Contact, contact_id)
            if workspace is None or contact is None:
                self.logger.warning(
                    "speed_to_lead_target_missing",
                    workspace_id=str(workspace_id),
                    contact_id=contact_id,
                    source=str(job.get("source", "")),
                )
                return

            gate_reason = config_gate(workspace, contact)
            if gate_reason is not None:
                self.logger.info(
                    "speed_to_lead_skipped",
                    reason=gate_reason,
                    workspace_id=str(workspace_id),
                    contact_id=contact_id,
                )
                return

            if (contact.sms_consent_status or "") == "opted_out":
                await self._audit(
                    db,
                    workspace_id=workspace_id,
                    contact_id=contact_id,
                    action_type=_SMS_ACTION,
                    decision="blocked",
                    reason="contact_opted_out",
                    payload=_audit_payload(job),
                )
                await db.commit()
                return

            quiet = quiet_hours_config(workspace)
            now = datetime.now(UTC)
            results = await self._evaluate_channels(
                db,
                workspace_id=workspace_id,
                contact=contact,
                channels=channels,
                campaign=build_compliance_campaign(workspace_id, quiet),
                now=now,
            )
            blocked = {name: result for name, result in results.items() if not result.allowed}
            allowed = {name: result for name, result in results.items() if result.allowed}
            if blocked:
                await self._audit_blocked(
                    db,
                    job=job,
                    workspace_id=workspace_id,
                    contact_id=contact_id,
                    blocked=blocked,
                    quiet=quiet,
                    attempts=attempts,
                    now=now,
                )
            if allowed:
                message_ids = await self._execute_channels(
                    db,
                    workspace_id=workspace_id,
                    contact=contact,
                    channels=tuple(allowed),
                )
                # Commit provider Message rows before the audit rows: if the
                # audit commit then fails, the retry resolves against the
                # committed idempotency key and never re-dials or re-texts.
                await db.commit()
                for channel, message_id in message_ids.items():
                    await self._audit(
                        db,
                        workspace_id=workspace_id,
                        contact_id=contact_id,
                        action_type=action_for_channel(channel),
                        decision="executed",
                        reason=None,
                        compliance=allowed[channel].as_dict(),
                        message_id=message_id,
                        payload=_audit_payload(job),
                    )
            await db.commit()

    async def _evaluate_channels(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        contact: Contact,
        channels: tuple[str, ...],
        campaign: Campaign,
        now: datetime,
    ) -> dict[str, OutboundComplianceResult]:
        """Run the shared outbound compliance gate once per requested channel."""
        results: dict[str, OutboundComplianceResult] = {}
        for channel in channels:
            results[channel] = await self.compliance.evaluate(
                OutboundComplianceRequest(
                    workspace_id=workspace_id,
                    campaign=campaign,
                    campaign_contact=None,
                    contact=contact,
                    channel=channel,
                    action_type=action_for_channel(channel),
                    now=now,
                    # The lead handed over their number by submitting the
                    # form/widget moments ago, so first-touch SMS runs without
                    # a prior opt-in — the same policy as the missed-call
                    # textback. Global opt-out and quiet hours are still
                    # enforced by this gate and again inside delivery.
                    require_sms_consent=False,
                ),
                db,
            )
        return results

    async def _audit_blocked(
        self,
        db: AsyncSession,
        *,
        job: dict[str, Any],
        workspace_id: uuid.UUID,
        contact_id: int,
        blocked: dict[str, OutboundComplianceResult],
        quiet: dict[str, Any],
        attempts: int,
        now: datetime,
    ) -> None:
        """Audit every blocked channel; reschedule when quiet hours own them all."""
        payload = _audit_payload(job)
        for channel, result in blocked.items():
            await self._audit(
                db,
                workspace_id=workspace_id,
                contact_id=contact_id,
                action_type=action_for_channel(channel),
                decision="blocked",
                reason=result.reason,
                compliance=result.as_dict(),
                payload=payload,
            )
        if CHANNEL_VOICE not in blocked or not owned_by_quiet_hours(blocked):
            return
        if attempts >= self.MAX_DEFERRALS:
            self.logger.warning(
                "speed_to_lead_deferral_budget_used",
                contact_id=contact_id,
                attempts=attempts,
            )
            return
        run_at = next_quiet_hours_end(quiet, now)
        if run_at is None:
            return
        client = await get_redis()
        rescheduled = {**job, "attempts": attempts + 1}
        await client.zadd(
            DELAYED_QUEUE_KEY,
            {json.dumps(rescheduled, sort_keys=True): run_at.timestamp()},
        )
        self.logger.info(
            "speed_to_lead_deferred_quiet_hours",
            contact_id=contact_id,
            run_at=run_at.isoformat(),
        )

    async def _execute_channels(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        contact: Contact,
        channels: tuple[str, ...],
    ) -> dict[str, uuid.UUID | None]:
        """Fire allowed channels in parallel; return channels actually attempted.

        Each send opens its own DB session — an ``AsyncSession`` must not be
        used by two coroutines at once.
        """
        agent_id = await self._resolve_agent_id(db, workspace_id)
        coroutines: dict[str, Awaitable[uuid.UUID | None]] = {}
        if CHANNEL_VOICE in channels:
            voice_from = await self._resolve_from_number(db, contact.id, workspace_id, voice=True)
            if voice_from is None:
                self.logger.warning("speed_to_lead_no_voice_number", workspace_id=str(workspace_id))
            else:
                coroutines[CHANNEL_VOICE] = self._dial_first_touch(
                    workspace_id=workspace_id,
                    contact_id=contact.id,
                    contact_phone=contact.phone_number,
                    agent_id=agent_id,
                    from_number=voice_from,
                )
        if CHANNEL_SMS in channels:
            sms_from = await self._resolve_from_number(db, contact.id, workspace_id, voice=False)
            if sms_from is None:
                self.logger.warning("speed_to_lead_no_sms_number", workspace_id=str(workspace_id))
            else:
                coroutines[CHANNEL_SMS] = self._send_first_touch_sms(
                    workspace_id=workspace_id,
                    contact_id=contact.id,
                    agent_id=agent_id,
                    from_number=sms_from,
                )
        if not coroutines:
            return {}
        names = list(coroutines)
        outcomes = await asyncio.gather(*coroutines.values(), return_exceptions=True)
        attempted: dict[str, uuid.UUID | None] = {}
        for name, outcome in zip(names, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                # Surface send failures so retry/backoff runs; idempotency keys
                # guarantee a replay after commit cannot double-dial or text.
                raise outcome
            attempted[name] = outcome
        return attempted

    # -------------------------------------------------------------------------
    # Channel sends (own session each — safe to run concurrently)
    # -------------------------------------------------------------------------

    async def _dial_first_touch(
        self,
        *,
        workspace_id: uuid.UUID,
        contact_id: int,
        contact_phone: str,
        agent_id: uuid.UUID | None,
        from_number: str,
    ) -> uuid.UUID:
        """Place the instant outbound voice attempt; return the Message id."""
        async with AsyncSessionLocal() as db:
            voice_service = TelnyxVoiceService(settings.telnyx_api_key)
            try:
                api_base = settings.api_base_url or "http://localhost:8000"
                message = await voice_service.initiate_call(
                    to_number=contact_phone,
                    from_number=from_number,
                    connection_id=settings.telnyx_connection_id or None,
                    webhook_url=f"{api_base}/webhooks/telnyx/voice",
                    db=db,
                    workspace_id=workspace_id,
                    contact_phone=contact_phone,
                    agent_id=agent_id,
                    idempotency_key=derive_outbound_key(
                        _DIAL_IDEMPOTENCY_SCOPE, workspace_id, contact_id
                    ),
                )
                await db.commit()
            finally:
                await voice_service.close()
        self.logger.info(
            "speed_to_lead_dial_started",
            workspace_id=str(workspace_id),
            contact_id=contact_id,
            message_id=str(message.id),
        )
        return message.id

    async def _send_first_touch_sms(
        self,
        *,
        workspace_id: uuid.UUID,
        contact_id: int,
        agent_id: uuid.UUID | None,
        from_number: str,
    ) -> uuid.UUID | None:
        """Send the parallel "we're calling you now" text via unified delivery.

        Provider failures are logged, not raised: the voice attempt is the
        primary touch and already runs in parallel, so one SMS blip must not
        fail the whole job (the workspace's campaigns still follow up).
        """
        async with AsyncSessionLocal() as db:
            contact = await db.get(Contact, contact_id)
            if contact is None:
                return None
            name = contact.first_name or "there"
            result = await outbound_delivery_service.deliver(
                db,
                OutboundDeliveryRequest(
                    workspace_id=workspace_id,
                    channel=OutboundDeliveryChannel.SMS,
                    to=contact.phone_number,
                    from_=from_number,
                    body=f"Hi {name}! Thanks for reaching out — we're calling you now.",
                    contact=contact,
                    agent_id=agent_id,
                    idempotency_scope=_SMS_IDEMPOTENCY_SCOPE,
                    idempotency_parts=(str(workspace_id), str(contact_id)),
                    action_type=_SMS_ACTION,
                    require_sms_consent=False,
                ),
            )
            if result.status is OutboundDeliveryStatus.BLOCKED:
                self.logger.info(
                    "speed_to_lead_sms_blocked",
                    reason=result.reason,
                    contact_id=contact_id,
                )
                return None
            if not result.delivered or result.message is None:
                self.logger.warning(
                    "speed_to_lead_sms_failed",
                    reason=result.reason,
                    contact_id=contact_id,
                )
                return None
            await db.commit()
        return result.message.id

    # -------------------------------------------------------------------------
    # Resolvers + audit
    # -------------------------------------------------------------------------

    async def _resolve_agent_id(
        self, db: AsyncSession, workspace_id: uuid.UUID
    ) -> uuid.UUID | None:
        """Return the workspace's oldest active agent (never creates one)."""
        result = await db.execute(
            select(Agent.id)
            .where(
                and_(
                    Agent.workspace_id == workspace_id,
                    Agent.is_active.is_(True),
                )
            )
            .order_by(Agent.created_at)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _resolve_from_number(
        self,
        db: AsyncSession,
        contact_id: int,
        workspace_id: uuid.UUID,
        *,
        voice: bool,
    ) -> str | None:
        """Resolve the sender number (conversation reuse, then capability)."""
        # Strategy 1 — reuse the number from an existing conversation.
        result = await db.execute(
            select(Conversation.workspace_phone)
            .where(
                and_(
                    Conversation.contact_id == contact_id,
                    Conversation.workspace_id == workspace_id,
                )
            )
            .order_by(Conversation.last_message_at.desc().nulls_last())
            .limit(1)
        )
        phone = result.scalar_one_or_none()
        if phone:
            return str(phone)

        # Strategy 2 — any active workspace number with the needed capability.
        capability = (
            PhoneNumber.voice_enabled.is_(True) if voice else PhoneNumber.sms_enabled.is_(True)
        )
        result = await db.execute(
            select(PhoneNumber.phone_number)
            .where(
                and_(
                    PhoneNumber.workspace_id == workspace_id,
                    PhoneNumber.is_active.is_(True),
                    capability,
                )
            )
            .order_by(PhoneNumber.created_at)
            .limit(1)
        )
        phone = result.scalar_one_or_none()
        if phone:
            return str(phone)
        return None

    async def _audit(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        contact_id: int,
        action_type: str,
        decision: str,
        reason: str | None,
        payload: dict[str, Any],
        compliance: dict[str, object] | None = None,
        message_id: uuid.UUID | None = None,
    ) -> None:
        """Append one outbound-action audit row (committed by the caller)."""
        db.add(
            OutboundActionAuditLog(
                workspace_id=workspace_id,
                contact_id=contact_id,
                action_type=action_type,
                action_payload=payload,
                compliance_result=compliance,
                decision=decision,
                reason=reason,
                source=_AUDIT_SOURCE,
                message_id=message_id,
            )
        )


# ---------------------------------------------------------------------------
# Pure helpers (module level so tests can exercise them without a DB)
# ---------------------------------------------------------------------------


def config_gate(workspace: Workspace, contact: Contact) -> str | None:
    """Return why this job must not run at all, or None when it may."""
    if not get_speed_to_lead_settings(workspace).enabled:
        return "speed_to_lead_disabled"
    mandate = normalize_autonomy_mandate(workspace.autonomy_mandate)
    if not (mandate.get("enabled") and mandate.get("auto_send_first_touches")):
        return "autonomy_mandate_blocks_first_touch"
    if not contact.phone_number:
        return "missing_phone_number"
    if not settings.telnyx_api_key:
        return "telnyx_not_configured"
    return None


def quiet_hours_config(workspace: Workspace) -> dict[str, Any]:
    """Return the autonomy mandate's quiet-hours policy ({} when unset)."""
    quiet = normalize_autonomy_mandate(workspace.autonomy_mandate).get("quiet_hours")
    return dict(quiet) if isinstance(quiet, dict) else {}


def build_compliance_campaign(workspace_id: uuid.UUID, quiet: dict[str, Any]) -> Campaign:
    """Build the transient campaign row carrying quiet-hours policy.

    ``OutboundComplianceRequest`` requires a campaign; quiet hours are
    evaluated off its ``quiet_hours_*`` fields. The instance is never added to
    a session — the mandate's quiet-hours policy is injected directly, and
    unset send-cap fields short-circuit to "no cap" inside the evaluator.
    """
    campaign = Campaign(workspace_id=workspace_id, name="Speed to Lead (instant)")
    if quiet.get("enabled"):
        campaign.quiet_hours_start = _parse_clock(quiet.get("start"))
        campaign.quiet_hours_end = _parse_clock(quiet.get("end"))
        timezone_name = quiet.get("timezone")
        if isinstance(timezone_name, str):
            campaign.quiet_hours_timezone = timezone_name
    return campaign


def owned_by_quiet_hours(blocked: dict[str, OutboundComplianceResult]) -> bool:
    """True when every blocked channel was blocked by quiet hours only."""
    return bool(blocked) and all(result.reason == "quiet_hours" for result in blocked.values())


def next_quiet_hours_end(quiet: dict[str, Any], now: datetime) -> datetime | None:
    """Return the next moment quiet hours end, or None when not deferable."""
    if not quiet.get("enabled"):
        return None
    end = _parse_clock(quiet.get("end"))
    if end is None:
        return None
    try:
        timezone_name = str(quiet.get("timezone") or "UTC")
        tz = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")
    local = now.astimezone(tz)
    candidate = local.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate


def action_for_channel(channel: str) -> str:
    """Return the compliance/audit action type for a first-touch channel."""
    if channel == CHANNEL_VOICE:
        return _VOICE_ACTION
    return _SMS_ACTION


def _audit_payload(job: dict[str, Any]) -> dict[str, Any]:
    """Small audit payload: where the job came from and how often it retried."""
    return {
        "source": str(job.get("source", "")),
        "attempts": _as_int(job.get("attempts")),
    }


def _as_int(value: Any) -> int:
    """Coerce a job field to int, defaulting to 0 on junk."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _parse_clock(value: Any) -> time | None:
    """Parse an ``HH:MM`` string into a ``time``, or None when malformed."""
    try:
        hour_text, minute_text = str(value).split(":")
        return time(int(hour_text) % 24, int(minute_text) % 60)
    except (AttributeError, TypeError, ValueError):
        return None


_registry = WorkerRegistry(SpeedToLeadWorker)
start_speed_to_lead_worker = _registry.start
stop_speed_to_lead_worker = _registry.stop
get_speed_to_lead_worker = _registry.get
