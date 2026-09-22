"""Operator reporting service — flips the Today system from pull to push.

Per workspace (when the autonomy mandate enables ``operator_report``), this
service composes three proactive iMessage reports to the operator's phone:

* **morning** — today's ordered mission plan (from :class:`TodayQueueService`);
* **eod** — an end-of-day recap of what the floor did, sold, and is blocked on;
* **escalation** — an immediate human-handoff ping when a buyer wants add-ons
  beyond the batch (running ads, AI-agent install, consulting).

Delivery reuses :data:`outbound_delivery_service` over
:attr:`OutboundDeliveryChannel.IMESSAGE` (the same rails the nudge and approval
delivery services use), so quiet hours, opt-out, and idempotency all flow
through the unified outbound facade. Quiet hours and once-per-day idempotency
are enforced here so the operator gets exactly one morning and one EOD per day.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_payment import CallPayment, CallPaymentStatus
from app.models.conversation import Conversation, Message, MessageDirection
from app.models.pending_action import PendingAction
from app.models.phone_number import PhoneNumber, PhoneNumberProvider
from app.models.workspace import Workspace
from app.services.autonomy_mandate import normalize_autonomy_mandate
from app.services.dashboard.setup_prerequisites import (
    SetupPrerequisiteReport,
    SetupPrerequisiteService,
)
from app.services.dashboard.today_queue_service import TodayQueueService
from app.services.outbound.delivery import (
    OutboundDeliveryChannel,
    OutboundDeliveryRequest,
    outbound_delivery_service,
)
from app.services.telephony.phone_number_resolver import get_workspace_sms_number

logger = structlog.get_logger()

# PendingAction.action_type used for buyer requests beyond the batch that must be
# handed to a human (running ads, AI-agent install, consulting). The autonomous
# closer parks these instead of acting; this service pushes them to the operator.
HUMAN_ESCALATION_ACTION_TYPE = "human_escalation"

# Settings key holding once-per-day delivery state: {"morning": date, "eod": date}.
_STATE_KEY = "operator_report_state"

# Settings key holding setup-prerequisite chase state:
# {"unmet_signature": str, "last_chased_date": "YYYY-MM-DD", "last_chased_at": iso}.
# Re-chase fires when the unmet set changes (progress/regression) or a new local
# day begins; it clears once every prerequisite is met so a later regression
# chases again immediately.
_CHASE_STATE_KEY = "setup_prerequisite_chase_state"

_DEFAULT_TIMEZONE = "America/New_York"
_DEFAULT_MORNING_HOUR = 8
_DEFAULT_EOD_HOUR = 18
_MAX_PLAN_ITEMS = 6
_TOP_BLOCKERS = 3


@dataclass(slots=True, frozen=True)
class OperatorReportResult:
    """Outcome of one workspace reporting pass."""

    workspace_id: uuid.UUID
    delivered: tuple[str, ...]
    skipped_reason: str | None = None


class OperatorReportService:
    """Builds and delivers proactive operator reports over iMessage."""

    async def run_for_workspace(
        self, db: AsyncSession, workspace: Workspace, *, now: datetime | None = None
    ) -> OperatorReportResult:
        """Run morning / EOD / escalation reporting for a single workspace.

        Idempotent: at most one morning and one EOD per local day. Escalations
        are deduped by ``PendingAction.notification_sent``. Quiet hours suppress
        every channel; suppressed reports are simply retried on the next cycle.
        """
        mandate = normalize_autonomy_mandate(workspace.autonomy_mandate)
        report_cfg = mandate.get("operator_report") or {}
        if not mandate.get("enabled", True) or not report_cfg.get("enabled", True):
            return OperatorReportResult(workspace.id, (), "report_disabled")

        recipient = self._resolve_recipient(workspace, report_cfg)
        if not recipient:
            return OperatorReportResult(workspace.id, (), "no_operator_phone")

        phone = await get_workspace_sms_number(db, workspace.id)
        if phone is None:
            return OperatorReportResult(workspace.id, (), "no_sender_number")

        now = now or datetime.now(UTC)
        tz = self._resolve_timezone(mandate)
        now_local = now.astimezone(tz)

        if self._in_quiet_hours(now_local, mandate):
            return OperatorReportResult(workspace.id, (), "quiet_hours")

        delivered: list[str] = []

        # Escalations are time-sensitive — handle them first each cycle.
        delivered.extend(await self._deliver_escalations(db, workspace, recipient, phone))

        # Setup prerequisites gate everything else — chase before the daily plan.
        chase = await self._maybe_prerequisite_chase(db, workspace, recipient, phone, now_local)
        if chase:
            delivered.append(chase)

        morning = await self._maybe_morning(db, workspace, recipient, phone, now_local, report_cfg)
        if morning:
            delivered.append(morning)

        eod = await self._maybe_eod(db, workspace, recipient, phone, now_local, report_cfg)
        if eod:
            delivered.append(eod)

        return OperatorReportResult(workspace.id, tuple(delivered))

    # ── morning plan ──────────────────────────────────────────────────

    async def _maybe_morning(
        self,
        db: AsyncSession,
        workspace: Workspace,
        recipient: str,
        phone: PhoneNumber,
        now_local: datetime,
        report_cfg: dict[str, Any],
    ) -> str | None:
        morning_hour = _bounded_hour(report_cfg.get("morning_hour"), _DEFAULT_MORNING_HOUR)
        eod_hour = _bounded_hour(report_cfg.get("eod_hour"), _DEFAULT_EOD_HOUR)
        if not (morning_hour <= now_local.hour < eod_hour):
            return None
        if self._already_sent(workspace, "morning", now_local):
            return None

        body = await self._build_morning_body(db, workspace, now_local)
        ok = await self._deliver(
            db,
            workspace,
            recipient,
            phone,
            body,
            scope="operator_report_morning",
            parts=(workspace.id, now_local.date().isoformat()),
        )
        if not ok:
            return None
        self._mark_sent(workspace, "morning", now_local)
        await db.commit()
        return "morning"

    async def _build_morning_body(
        self, db: AsyncSession, workspace: Workspace, now_local: datetime
    ) -> str:
        queue = await TodayQueueService(db).get_today_queue(workspace.id)
        header = f"☀️ Morning — {workspace.name}. Today's plan:"
        if not queue.items:
            return (
                f"{header}\nNothing queued. The floor is quiet — I'll keep prospecting "
                "the batch and report back tonight."
            )
        lines = [
            f"{idx}. {item.title}"
            for idx, item in enumerate(queue.items[:_MAX_PLAN_ITEMS], start=1)
        ]
        extra = len(queue.items) - _MAX_PLAN_ITEMS
        if extra > 0:
            lines.append(f"…+{extra} more")
        footer = "I'm running the floor over iMessage. Reply here to redirect me."
        return f"{header}\n" + "\n".join(lines) + f"\n{footer}"

    # ── end-of-day recap ──────────────────────────────────────────────

    async def _maybe_eod(
        self,
        db: AsyncSession,
        workspace: Workspace,
        recipient: str,
        phone: PhoneNumber,
        now_local: datetime,
        report_cfg: dict[str, Any],
    ) -> str | None:
        eod_hour = _bounded_hour(report_cfg.get("eod_hour"), _DEFAULT_EOD_HOUR)
        if now_local.hour < eod_hour:
            return None
        if self._already_sent(workspace, "eod", now_local):
            return None

        body = await self._build_eod_body(db, workspace, now_local)
        ok = await self._deliver(
            db,
            workspace,
            recipient,
            phone,
            body,
            scope="operator_report_eod",
            parts=(workspace.id, now_local.date().isoformat()),
        )
        if not ok:
            return None
        self._mark_sent(workspace, "eod", now_local)
        await db.commit()
        return "eod"

    async def _build_eod_body(
        self, db: AsyncSession, workspace: Workspace, now_local: datetime
    ) -> str:
        day_start, day_end = self._local_day_bounds(now_local)

        sold_count, sold_total = await self._payments_today(db, workspace.id, day_start, day_end)
        sent = await self._outbound_today(db, workspace.id, day_start, day_end)
        replies = await self._inbound_today(db, workspace.id, day_start, day_end)
        blocked_count, blockers = await self._open_blockers(db, workspace.id)

        sold_line = (
            f"Sold: {sold_count} pack{_s(sold_count)} for {_money(sold_total)}"
            if sold_count
            else "Sold: nothing closed today yet"
        )
        did_line = (
            f"Did: {sent} message{_s(sent)} out, {replies} repl{'ies' if replies != 1 else 'y'} in"
        )
        if blocked_count:
            top = "; ".join(_truncate(b) for b in blockers)
            blocked_line = f"Blocked: {blocked_count} waiting on you — {top}"
        else:
            blocked_line = "Blocked: nothing — you're clear"

        return f"🌙 EOD recap — {workspace.name}\n{sold_line}\n{did_line}\n{blocked_line}"

    # ── escalations (immediate human-handoff) ─────────────────────────

    async def _deliver_escalations(
        self,
        db: AsyncSession,
        workspace: Workspace,
        recipient: str,
        phone: PhoneNumber,
    ) -> list[str]:
        result = await db.execute(
            select(PendingAction)
            .where(
                PendingAction.workspace_id == workspace.id,
                PendingAction.action_type == HUMAN_ESCALATION_ACTION_TYPE,
                PendingAction.status == "pending",
                PendingAction.notification_sent.is_(False),
            )
            .order_by(PendingAction.created_at.asc())
        )
        actions = list(result.scalars().all())
        delivered: list[str] = []
        for action in actions:
            body = self._build_escalation_body(action)
            ok = await self._deliver(
                db,
                workspace,
                recipient,
                phone,
                body,
                scope="operator_report_escalation",
                parts=(action.id,),
            )
            if not ok:
                continue
            action.notification_sent = True
            action.notification_sent_at = datetime.now(UTC)
            await db.commit()
            delivered.append("escalation")
        return delivered

    def _build_escalation_body(self, action: PendingAction) -> str:
        context = action.context or {}
        who = context.get("company_name") or context.get("contact_name") or "a buyer"
        label = context.get("escalation_label") or "an add-on beyond the batch"
        return (
            f"🚨 Human-handoff — {who}\n{_truncate(action.description, 200)}\n"
            f"This is beyond the batch ({label}). Want me to hold or hand it to you?"
        )

    # ── setup-prerequisite chase (owned to-dos until unblocked) ───────

    async def _maybe_prerequisite_chase(
        self,
        db: AsyncSession,
        workspace: Workspace,
        recipient: str,
        phone: PhoneNumber,
        now_local: datetime,
    ) -> str | None:
        """Chase the operator about unmet setup prerequisites.

        Each unmet prerequisite is an owned to-do The Tribunal nags about until
        it is resolved. The chase is anti-spam: at most once per local day for a
        stable unmet set, but fires immediately when the set changes (a gap was
        resolved or a new one appeared) so progress is reflected and resolved
        items are never repeated. When everything is met the chase state clears.
        """
        report = await SetupPrerequisiteService(db).evaluate(workspace.id)
        state = (workspace.settings or {}).get(_CHASE_STATE_KEY) or {}

        if report.all_met:
            if state:
                self._clear_chase_state(workspace)
                await db.commit()
            return None

        signature = report.unmet_signature
        today = now_local.date().isoformat()
        if state.get("unmet_signature") == signature and state.get("last_chased_date") == today:
            return None

        body = self._build_prerequisite_chase_body(workspace, report)
        ok = await self._deliver(
            db,
            workspace,
            recipient,
            phone,
            body,
            scope="operator_report_prerequisite_chase",
            parts=(workspace.id, today, signature),
        )
        if not ok:
            return None
        self._set_chase_state(workspace, signature, now_local)
        await db.commit()
        return "prerequisite_chase"

    def _build_prerequisite_chase_body(
        self, workspace: Workspace, report: SetupPrerequisiteReport
    ) -> str:
        blocked = _join_natural([p.short_title for p in report.unmet])
        header = (
            f"🧩 Setup — {workspace.name}. To run prestyj sales I have "
            f"{report.met_count} of {report.total} prerequisites ready. "
            f"I'm blocked on {blocked} — here's the 2-minute fix for each:"
        )
        lines = [f"• {_sentence_case(p.short_title)}: {p.fix}" for p in report.unmet]
        footer = (
            "Knock these out and I'll start selling the batch. "
            "I'll keep reminding you until they're done."
        )
        return f"{header}\n" + "\n".join(lines) + f"\n{footer}"

    def _clear_chase_state(self, workspace: Workspace) -> None:
        settings = dict(workspace.settings or {})
        settings.pop(_CHASE_STATE_KEY, None)
        workspace.settings = settings

    def _set_chase_state(self, workspace: Workspace, signature: str, now_local: datetime) -> None:
        settings = dict(workspace.settings or {})
        settings[_CHASE_STATE_KEY] = {
            "unmet_signature": signature,
            "last_chased_date": now_local.date().isoformat(),
            "last_chased_at": now_local.astimezone(UTC).isoformat(),
        }
        # Reassign so SQLAlchemy tracks the JSONB mutation.
        workspace.settings = settings

    # ── delivery + idempotency state ──────────────────────────────────

    async def _deliver(
        self,
        db: AsyncSession,
        workspace: Workspace,
        recipient: str,
        phone: PhoneNumber,
        body: str,
        *,
        scope: str,
        parts: tuple[object, ...],
    ) -> bool:
        channel = (
            OutboundDeliveryChannel.IMESSAGE
            if phone.provider is PhoneNumberProvider.MAC_RELAY or phone.imessage_enabled
            else OutboundDeliveryChannel.SMS
        )
        try:
            result = await outbound_delivery_service.deliver(
                db,
                OutboundDeliveryRequest(
                    workspace_id=workspace.id,
                    channel=channel,
                    to=recipient,
                    from_=phone.phone_number,
                    body=body,
                    phone_number_id=phone.id,
                    idempotency_scope=scope,
                    idempotency_parts=parts,
                    action_type=scope,
                ),
            )
        except Exception:
            logger.exception(
                "operator_report_delivery_failed",
                workspace_id=str(workspace.id),
                scope=scope,
            )
            return False

        logger.info(
            "operator_report_delivery",
            workspace_id=str(workspace.id),
            scope=scope,
            channel=channel.value,
            status=result.status.value,
            delivered=result.delivered,
        )
        return result.delivered

    def _already_sent(self, workspace: Workspace, kind: str, now_local: datetime) -> bool:
        state = (workspace.settings or {}).get(_STATE_KEY) or {}
        return state.get(kind) == now_local.date().isoformat()

    def _mark_sent(self, workspace: Workspace, kind: str, now_local: datetime) -> None:
        settings = dict(workspace.settings or {})
        state = dict(settings.get(_STATE_KEY) or {})
        state[kind] = now_local.date().isoformat()
        settings[_STATE_KEY] = state
        # Reassign so SQLAlchemy tracks the JSONB mutation.
        workspace.settings = settings

    # ── recipient + quiet-hours helpers ───────────────────────────────

    def _resolve_recipient(self, workspace: Workspace, report_cfg: dict[str, Any]) -> str | None:
        phone = report_cfg.get("phone")
        if isinstance(phone, str) and phone.strip():
            return phone.strip()
        settings_phone = (workspace.settings or {}).get("operator_report_phone")
        if isinstance(settings_phone, str) and settings_phone.strip():
            return settings_phone.strip()
        return None

    def _resolve_timezone(self, mandate: dict[str, Any]) -> ZoneInfo:
        quiet = mandate.get("quiet_hours") or {}
        name = quiet.get("timezone") or ((mandate.get("operator_report") or {}).get("timezone"))
        for candidate in (name, _DEFAULT_TIMEZONE):
            if not candidate:
                continue
            try:
                return ZoneInfo(candidate)
            except (ZoneInfoNotFoundError, ValueError):
                continue
        return ZoneInfo("UTC")

    def _in_quiet_hours(self, now_local: datetime, mandate: dict[str, Any]) -> bool:
        quiet = mandate.get("quiet_hours") or {}
        if not quiet.get("enabled", True):
            return False
        start = _parse_minutes(quiet.get("start"), default=20 * 60)
        end = _parse_minutes(quiet.get("end"), default=8 * 60)
        current = now_local.hour * 60 + now_local.minute
        if start > end:  # spans midnight (e.g. 20:00 – 08:00)
            return current >= start or current < end
        return start <= current < end

    def _local_day_bounds(self, now_local: datetime) -> tuple[datetime, datetime]:
        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = now_local
        return start_local.astimezone(UTC), end_local.astimezone(UTC)

    # ── EOD data queries ──────────────────────────────────────────────

    async def _payments_today(
        self, db: AsyncSession, workspace_id: uuid.UUID, day_start: datetime, day_end: datetime
    ) -> tuple[int, Decimal]:
        result = await db.execute(
            select(
                func.count(CallPayment.id), func.coalesce(func.sum(CallPayment.amount), 0)
            ).where(
                CallPayment.workspace_id == workspace_id,
                CallPayment.status == CallPaymentStatus.PAID,
                CallPayment.paid_at >= day_start,
                CallPayment.paid_at <= day_end,
            )
        )
        count, total = result.one()
        return int(count or 0), Decimal(str(total or 0))

    async def _outbound_today(
        self, db: AsyncSession, workspace_id: uuid.UUID, day_start: datetime, day_end: datetime
    ) -> int:
        result = await db.execute(
            select(func.count(Message.id))
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Conversation.workspace_id == workspace_id,
                Message.direction == MessageDirection.OUTBOUND,
                Message.created_at >= day_start,
                Message.created_at <= day_end,
            )
        )
        return int(result.scalar() or 0)

    async def _inbound_today(
        self, db: AsyncSession, workspace_id: uuid.UUID, day_start: datetime, day_end: datetime
    ) -> int:
        result = await db.execute(
            select(func.count(Message.id))
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Conversation.workspace_id == workspace_id,
                Message.direction == MessageDirection.INBOUND,
                Message.created_at >= day_start,
                Message.created_at <= day_end,
            )
        )
        return int(result.scalar() or 0)

    async def _open_blockers(
        self, db: AsyncSession, workspace_id: uuid.UUID
    ) -> tuple[int, list[str]]:
        count_result = await db.execute(
            select(func.count(PendingAction.id)).where(
                PendingAction.workspace_id == workspace_id,
                PendingAction.status == "pending",
            )
        )
        count = int(count_result.scalar() or 0)
        if count == 0:
            return 0, []
        top_result = await db.execute(
            select(PendingAction.description)
            .where(
                PendingAction.workspace_id == workspace_id,
                PendingAction.status == "pending",
            )
            .order_by(PendingAction.created_at.desc())
            .limit(_TOP_BLOCKERS)
        )
        return count, [row[0] for row in top_result.all()]


def _parse_minutes(value: object, *, default: int) -> int:
    if not isinstance(value, str):
        return default
    try:
        hour, minute = (int(part) for part in value.split(":"))
    except (ValueError, AttributeError):
        return default
    return hour * 60 + minute


def _bounded_hour(value: object, default: int) -> int:
    if not isinstance(value, (int, str)):
        return default
    try:
        hour = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, min(hour, 23))


def _money(total: Decimal) -> str:
    return f"${total:,.0f}" if total == total.to_integral_value() else f"${total:,.2f}"


def _s(count: int) -> str:
    return "s" if count != 1 else ""


def _sentence_case(text: str) -> str:
    """Capitalize the first letter only, preserving casing like 'SMS/iMessage'."""
    return text[:1].upper() + text[1:] if text else text


def _join_natural(items: list[str]) -> str:
    """Join phrases with commas and a trailing 'and' (Oxford-style)."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _truncate(text: str, limit: int = 120) -> str:
    cleaned = " ".join((text or "").split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "…"


operator_report_service = OperatorReportService()
