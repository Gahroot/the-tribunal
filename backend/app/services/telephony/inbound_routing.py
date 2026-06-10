"""Reason-based routing for inbound calls.

Once an inbound caller's intent ("reason") is known, the call can be routed to
the most appropriate agent/queue (e.g. billing vs sales vs support) instead of
always falling back to the phone number's default agent.

Two pieces live here:

* :func:`classify_inbound_reason` — an early, deterministic classifier that
  derives a reason from the caller's recent conversation history (returning
  callers). It is intentionally cheap and dependency-free so it can run inline
  on the ``call.initiated`` webhook before the call is answered. It returns
  ``None`` when no confident reason is found, in which case routing falls back
  to the default :class:`VoiceAgentResolver` priority order.

* The routing *map* itself is configured per workspace under
  ``workspace.settings["call_routing"]`` as ``{reason: agent_id}`` and is
  consumed by :meth:`VoiceAgentResolver.resolve` when a ``reason`` is supplied.

The live AI agent can also call back into :func:`classify_inbound_reason`-style
routing mid-call once it has gathered intent; this module keeps the keyword
heuristics in one place so both paths classify consistently.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Message, MessageDirection

logger = structlog.get_logger()

# Settings key under ``workspace.settings`` holding ``{reason: agent_id}``.
ROUTING_SETTINGS_KEY = "call_routing"

# Ordered keyword rules mapping recognised reasons to trigger terms. Order
# matters: the first reason with a matching keyword wins, so more specific
# intents (billing/support) are checked before broader ones (sales).
_REASON_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "billing",
        (
            "bill",
            "billing",
            "invoice",
            "payment",
            "charge",
            "refund",
            "subscription",
            "credit card",
            "overcharge",
        ),
    ),
    (
        "support",
        (
            "support",
            "help",
            "issue",
            "problem",
            "broken",
            "not working",
            "bug",
            "error",
            "cancel",
            "complaint",
        ),
    ),
    (
        "sales",
        (
            "buy",
            "purchase",
            "pricing",
            "price",
            "quote",
            "demo",
            "upgrade",
            "plan",
            "interested in",
            "sign up",
        ),
    ),
)

# How many recent messages from a returning caller to scan for intent terms.
_HISTORY_LOOKBACK = 10


def classify_reason_from_text(text: str | None) -> str | None:
    """Classify a caller reason from free text using keyword heuristics.

    Returns a canonical reason string (e.g. ``"billing"``) or ``None`` when no
    keyword matches. Shared by the early history-based classifier and any
    live, transcript-driven routing the agent performs mid-call.
    """
    if not text:
        return None
    haystack = text.lower()
    for reason, keywords in _REASON_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return reason
    return None


async def classify_inbound_reason(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    conversation: Any | None,
    log: Any | None = None,
) -> str | None:
    """Best-effort early classification of an inbound caller's reason.

    Uses the caller's recent inbound message history (returning callers) so the
    call can be routed before it is answered. Returns ``None`` for first-time
    callers or when no confident reason is found.

    Args:
        db: Database session.
        workspace_id: Workspace receiving the call.
        conversation: The inbound call's conversation (may be brand new).
        log: Optional bound logger.

    Returns:
        A canonical reason string or ``None``.
    """
    log = log or logger
    if conversation is None:
        return None

    # The freshly-created ringing message carries no transcript yet, so look at
    # what the caller said in prior inbound messages on this conversation.
    result = await db.execute(
        select(Message.body)
        .where(
            Message.conversation_id == conversation.id,
            Message.direction == MessageDirection.INBOUND,
        )
        .order_by(Message.created_at.desc())
        .limit(_HISTORY_LOOKBACK)
    )
    bodies = [b for (b,) in result.all() if b]

    # Also consider the denormalised last-message preview as a cheap signal.
    preview = getattr(conversation, "last_message_preview", None)
    if preview:
        bodies.append(preview)

    for body in bodies:
        reason = classify_reason_from_text(body)
        if reason:
            log.info("inbound_reason_classified", reason=reason)
            return reason

    return None


def resolve_routing_map(workspace_settings: dict[str, Any] | None) -> dict[str, uuid.UUID]:
    """Parse the ``call_routing`` reason→agent map from workspace settings."""
    raw = (workspace_settings or {}).get(ROUTING_SETTINGS_KEY, {})
    if not isinstance(raw, dict):
        return {}

    parsed: dict[str, uuid.UUID] = {}
    for reason, agent_id in raw.items():
        if not reason or not agent_id:
            continue
        try:
            parsed[str(reason).lower()] = uuid.UUID(str(agent_id))
        except (ValueError, AttributeError):
            continue
    return parsed


async def get_workspace_routing_map(
    db: AsyncSession,
    workspace_id: uuid.UUID,
) -> dict[str, uuid.UUID]:
    """Load and parse the reason→agent routing map for a workspace."""
    from app.models.workspace import Workspace

    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        return {}
    return resolve_routing_map(workspace.settings)


async def find_conversation_workspace_id(
    conversation: Any | None,
    phone_record: Any | None,
) -> uuid.UUID | None:
    """Return the workspace id from a conversation or phone record."""
    if conversation is not None and getattr(conversation, "workspace_id", None):
        ws_id: uuid.UUID = conversation.workspace_id
        return ws_id
    if phone_record is not None and getattr(phone_record, "workspace_id", None):
        ws_id = phone_record.workspace_id
        return ws_id
    return None
