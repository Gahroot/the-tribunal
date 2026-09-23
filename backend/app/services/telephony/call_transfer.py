"""Consent-gated warm call transfer (AI -> human closer) orchestration.

The closer receives a briefing on a separate leg, then presses 1 to accept.
Only then does the webhook stop AI streaming and bridge the caller. Pending
state is stored in Redis before dialing so an early answer is not missed.
The destination resolves from agent or workspace settings; cold mode is never
allowed, even when configured. Transfer attempts are audited.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from dataclasses import dataclass
from typing import Any

import structlog

from app.db.redis import get_redis
from app.services.idempotency import encode_client_state

logger = structlog.get_logger()

# Pending transfer state lives long enough for ringing, briefing, and confirmation.
_PENDING_TRANSFER_PREFIX = "voice:transfer:pending:"
_PENDING_TRANSFER_TTL_SECONDS = 180


@dataclass(frozen=True, slots=True)
class TransferResolution:
    """Resolved transfer configuration for an agent's active call."""

    destination_number: str
    mode: str  # always "warm"; retained for existing configuration consumers
    briefing_template: str | None


@dataclass(frozen=True, slots=True)
class PendingTransfer:
    """Warm-transfer state bridging the dial -> brief -> bridge handshake.

    Stored before dialing, keyed by the per-attempt token in Telnyx client_state.
    The closer confirms readiness with DTMF 1 after hearing the briefing.
    """

    caller_call_control_id: str
    closer_call_control_id: str
    workspace_id: str
    agent_id: str | None
    mode: str
    briefing: str
    language: str
    created_at: str
    briefing_completed: bool = False
    is_outbound: bool = False

    def to_json(self) -> str:
        return json.dumps(
            {
                "caller_call_control_id": self.caller_call_control_id,
                "closer_call_control_id": self.closer_call_control_id,
                "workspace_id": self.workspace_id,
                "agent_id": self.agent_id,
                "mode": self.mode,
                "briefing": self.briefing,
                "language": self.language,
                "created_at": self.created_at,
                "briefing_completed": self.briefing_completed,
                "is_outbound": self.is_outbound,
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> PendingTransfer:
        data = json.loads(raw)
        return cls(
            caller_call_control_id=data["caller_call_control_id"],
            closer_call_control_id=data["closer_call_control_id"],
            workspace_id=data["workspace_id"],
            agent_id=data.get("agent_id"),
            mode=data.get("mode", "warm"),
            briefing=data.get("briefing", ""),
            language=data.get("language", "en-US"),
            created_at=data.get("created_at", ""),
            briefing_completed=data.get("briefing_completed", False),
            is_outbound=data.get("is_outbound", False),
        )


def resolve_transfer_config(
    agent: Any,
    workspace_settings: dict[str, Any] | None,
) -> TransferResolution | None:
    """Resolve the destination number, mode, and briefing for a transfer.

    Precedence: per-agent ``transfer_destination_number`` then workspace
    ``settings["transfer_destination_number"]``. Returns None when no
    destination is configured (the AI should not be able to transfer to
    nowhere).
    """
    ws_settings = workspace_settings or {}

    destination = getattr(agent, "transfer_destination_number", None) or ws_settings.get(
        "transfer_destination_number"
    )
    if not destination:
        return None

    # Cold transfers are never permitted: the human must hear the briefing first.
    mode = "warm"

    briefing_template = getattr(agent, "transfer_briefing_template", None) or ws_settings.get(
        "transfer_briefing_template"
    )

    return TransferResolution(
        destination_number=str(destination),
        mode=mode,
        briefing_template=briefing_template,
    )


def build_briefing(
    *,
    template: str | None,
    caller_name: str,
    intent: str | None,
    summary: str | None,
) -> str:
    """Build the spoken warm-transfer briefing for the human closer.

    Uses the operator template (supports ``{caller_name}``, ``{intent}``,
    ``{summary}``) when provided, otherwise assembles a clean default sentence
    from whatever context the AI supplied.
    """
    intent_text = (intent or "").strip()
    summary_text = (summary or "").strip()
    name_text = (caller_name or "the caller").strip() or "the caller"

    if template:
        try:
            return template.format(
                caller_name=name_text,
                intent=intent_text or "to speak with someone",
                summary=summary_text,
            ).strip()
        except (KeyError, IndexError, ValueError):
            logger.warning("transfer_briefing_template_invalid")

    parts = [f"Connecting you to {name_text}."]
    if intent_text:
        parts.append(f"They want {intent_text}.")
    if summary_text:
        parts.append(summary_text)
    return " ".join(parts)


def make_transfer_leg_client_state(token: str) -> str:
    """Encode an unpredictable, per-attempt UUID for closer-leg webhooks."""
    return encode_client_state(uuid.UUID(token))


def transfer_key_from_client_state(state: str | None) -> str | None:
    """Decode the transfer key echoed by Telnyx; reject malformed state."""
    if not isinstance(state, str) or len(state) > 100:
        return None
    try:
        decoded = base64.b64decode(state, validate=True).decode("ascii")
        value = uuid.UUID(decoded)
        return str(value) if decoded == str(value) else None
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return None


async def claim_transfer_briefing(token: str) -> bool:
    """Speak the briefing at most once even if Telnyx retries call.answered."""
    try:
        client = await get_redis()
        return bool(
            await client.set(
                _PENDING_TRANSFER_PREFIX + "briefing:" + token,
                "1",
                nx=True,
                ex=_PENDING_TRANSFER_TTL_SECONDS,
            )
        )
    except Exception:
        logger.exception("claim_transfer_briefing_failed")
        return False


async def store_pending_transfer(pending: PendingTransfer) -> bool:
    """Persist pending state before dialing, keyed by its transfer token."""
    try:
        client = await get_redis()
        await client.set(
            _PENDING_TRANSFER_PREFIX + pending.closer_call_control_id,
            pending.to_json(),
            ex=_PENDING_TRANSFER_TTL_SECONDS,
        )
        return True
    except Exception as exc:
        logger.warning("store_pending_transfer_failed", error=str(exc))
        return False


async def peek_pending_transfer(closer_call_control_id: str) -> PendingTransfer | None:
    """Read pending state without deleting it before briefing or confirmation."""
    try:
        client = await get_redis()
        raw = await client.get(_PENDING_TRANSFER_PREFIX + closer_call_control_id)
        return PendingTransfer.from_json(raw) if raw is not None else None
    except Exception as exc:  # pragma: no cover - Redis best-effort
        logger.warning("peek_pending_transfer_failed", error=str(exc))
        return None


async def pop_pending_transfer(closer_call_control_id: str) -> PendingTransfer | None:
    """Atomically claim pending state by its per-attempt token."""
    try:
        client = await get_redis()
        # GETDEL claims the handoff atomically across webhook workers/replicas.
        raw = await client.getdel(_PENDING_TRANSFER_PREFIX + closer_call_control_id)
        return PendingTransfer.from_json(raw) if raw is not None else None
    except Exception as exc:  # pragma: no cover - Redis best-effort
        logger.warning("pop_pending_transfer_failed", error=str(exc))
        return None


async def log_transfer_audit(
    *,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID | None,
    message_id: uuid.UUID | None,
    contact_id: int | None,
    campaign_id: uuid.UUID | None,
    decision: str,
    reason: str,
    payload: dict[str, Any],
) -> None:
    """Append an immutable audit record for a transfer attempt.

    Mirrors the existing outbound-action audit trail so handoffs are visible in
    the same history as other AI actions. Best-effort: a logging failure must
    never abort an in-progress call transfer.
    """
    from app.db.session import AsyncSessionLocal
    from app.models.outbound_action_audit_log import OutboundActionAuditLog

    try:
        async with AsyncSessionLocal() as db:
            db.add(
                OutboundActionAuditLog(
                    workspace_id=workspace_id,
                    agent_id=agent_id,
                    action_type="transfer_call",
                    action_payload=payload,
                    decision=decision,
                    reason=reason,
                    source="voice_call",
                    contact_id=contact_id,
                    campaign_id=campaign_id,
                    message_id=message_id,
                )
            )
            await db.commit()
    except Exception as exc:  # pragma: no cover - audit is best-effort
        logger.warning("log_transfer_audit_failed", error=str(exc))
