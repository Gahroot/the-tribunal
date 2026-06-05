"""Live warm/cold call transfer (AI -> human closer) orchestration.

When an AI voice agent decides to hand an active call to a human, the
``transfer_call`` tool delegates here. Two modes are supported:

- **cold**: issue the native Telnyx ``transfer`` command immediately. Telnyx
  dials the closer and bridges them to the caller; the AI stops talking.
- **warm**: dial a *new* outbound leg to the closer, speak a 1-2 sentence
  briefing on that leg, then bridge it to the caller leg once the briefing
  finishes. The bridge half of the handshake is completed by the Telnyx voice
  webhook handler (``call.speak.ended``) using pending state we stash in Redis.

The destination number and mode resolve from the agent first, then workspace
``settings``. Every handoff is recorded in ``OutboundActionAuditLog`` so it
shows up alongside the rest of the outbound action history.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

import structlog

from app.db.redis import get_redis
from app.services.idempotency import encode_client_state

logger = structlog.get_logger()

# Redis key prefix for warm-transfer pending state keyed by the *new closer leg*
# call_control_id. The voice webhook handler reads this on call.speak.ended to
# know which caller leg to bridge into.
_PENDING_TRANSFER_PREFIX = "voice:transfer:pending:"
_PENDING_TRANSFER_TTL_SECONDS = 600  # 10 minutes; a transfer should resolve fast

# client_state marker so transfer-leg webhooks are recognizable.
TRANSFER_LEG_CLIENT_STATE_PREFIX = "transfer_leg"


@dataclass(frozen=True, slots=True)
class TransferResolution:
    """Resolved transfer configuration for an agent's active call."""

    destination_number: str
    mode: str  # "warm" | "cold"
    briefing_template: str | None


@dataclass(frozen=True, slots=True)
class PendingTransfer:
    """Warm-transfer state bridging the dial -> brief -> bridge handshake.

    Stored in Redis keyed by the *closer* leg's call_control_id. The voice
    webhook handler reads it twice: on ``call.answered`` (to speak ``briefing``
    on the closer leg) and on ``call.speak.ended`` (to bridge ``closer`` into
    ``caller_call_control_id``).
    """

    caller_call_control_id: str
    closer_call_control_id: str
    workspace_id: str
    agent_id: str | None
    mode: str
    briefing: str
    language: str
    created_at: str

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

    raw_mode = getattr(agent, "transfer_mode", None) or ws_settings.get("transfer_mode") or "warm"
    mode = str(raw_mode).lower()
    if mode not in {"warm", "cold"}:
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
    parts.append("Connecting you now.")
    return " ".join(parts)


def make_transfer_leg_client_state(token: str) -> str:
    """Return base64 client_state marking a dialed leg as a transfer leg."""
    raw = f"{TRANSFER_LEG_CLIENT_STATE_PREFIX}:{token}"
    return encode_client_state(uuid.uuid5(uuid.NAMESPACE_DNS, raw))


async def store_pending_transfer(pending: PendingTransfer) -> None:
    """Persist warm-transfer pending state keyed by the closer leg id."""
    try:
        client = await get_redis()
        await client.set(
            _PENDING_TRANSFER_PREFIX + pending.closer_call_control_id,
            pending.to_json(),
            ex=_PENDING_TRANSFER_TTL_SECONDS,
        )
    except Exception as exc:  # pragma: no cover - Redis best-effort
        logger.warning("store_pending_transfer_failed", error=str(exc))


async def peek_pending_transfer(closer_call_control_id: str) -> PendingTransfer | None:
    """Read warm-transfer pending state without deleting it.

    Used on ``call.answered`` for the closer leg so we can speak the briefing
    while leaving the state in place for the later bridge step.
    """
    try:
        client = await get_redis()
        raw = await client.get(_PENDING_TRANSFER_PREFIX + closer_call_control_id)
        return PendingTransfer.from_json(raw) if raw is not None else None
    except Exception as exc:  # pragma: no cover - Redis best-effort
        logger.warning("peek_pending_transfer_failed", error=str(exc))
        return None


async def pop_pending_transfer(closer_call_control_id: str) -> PendingTransfer | None:
    """Fetch and delete warm-transfer pending state for a closer leg id."""
    try:
        client = await get_redis()
        raw = await client.get(_PENDING_TRANSFER_PREFIX + closer_call_control_id)
        if raw is None:
            return None
        await client.delete(_PENDING_TRANSFER_PREFIX + closer_call_control_id)
        return PendingTransfer.from_json(raw)
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
