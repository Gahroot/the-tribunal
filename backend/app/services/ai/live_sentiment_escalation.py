"""Escalation orchestration for live (during-call) sentiment.

Turns :class:`~app.services.ai.live_sentiment.SentimentUpdate` events emitted
by the voice bridge into side effects:

- persists live ``sentiment`` / ``sentiment_score`` onto the call's
  ``CallOutcome.signals`` so the conversation timeline reflects caller mood
  *while the call is still active* (not just after the post-call worker);
- on a sustained-negativity escalation, emits a ``live_sentiment_escalation``
  log event, notifies workspace operators (push), and — when enabled and a
  transfer destination is configured — attempts an automatic human transfer.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.services.ai.call_outcome_service import upsert_live_call_signals
from app.services.ai.live_sentiment import SentimentUpdate

logger = structlog.get_logger()


async def _resolve_message_id(call_id: str) -> uuid.UUID | None:
    """Resolve the Message (call) UUID for a Telnyx call control id."""
    from sqlalchemy import select

    from app.models.conversation import Message

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Message.id).where(Message.provider_message_id == call_id))
        return result.scalar_one_or_none()


async def _persist_live_signals(
    message_id: uuid.UUID,
    update: SentimentUpdate,
    log: Any,
) -> None:
    """Merge the latest live sentiment onto the call's outcome signals."""
    signals: dict[str, Any] = {
        "sentiment": update.sentiment,
        "sentiment_score": round(update.score, 4),
        "sentiment_live": True,
    }
    if update.escalate:
        signals["sentiment_escalated"] = True
    try:
        async with AsyncSessionLocal() as db:
            await upsert_live_call_signals(db, message_id, signals)
    except Exception as e:
        log.warning("live_sentiment_persist_failed", error=str(e))


async def _notify_operators(
    workspace_id: uuid.UUID,
    update: SentimentUpdate,
    contact_info: dict[str, Any] | None,
    log: Any,
) -> None:
    """Push a negative-sentiment escalation alert to workspace operators."""
    from app.services.push_notifications import push_notification_service

    who = "the caller"
    if contact_info and contact_info.get("name"):
        who = contact_info["name"]

    title = "Call needs attention"
    body = f"Negative sentiment detected on a live call with {who}."[:300]

    try:
        async with AsyncSessionLocal() as db:
            await push_notification_service.send_to_workspace_members(
                db=db,
                workspace_id=str(workspace_id),
                title=title,
                body=body,
                data={
                    "type": "call",
                    "reason": "sentiment_escalation",
                    "sentiment_score": round(update.score, 4),
                    "screen": "/(tabs)/calls",
                },
                notification_type="call",
                channel_id="calls",
            )
    except Exception as e:
        log.warning("live_sentiment_notify_failed", error=str(e))


async def _maybe_auto_transfer(
    *,
    agent: Any,
    contact_info: dict[str, Any] | None,
    call_control_id: str | None,
    workspace_id: uuid.UUID,
    update: SentimentUpdate,
    log: Any,
) -> bool:
    """Attempt an automatic human transfer on escalation, if enabled.

    Returns True when a transfer was started. No-ops (returning False) when the
    feature flag is off, the agent has transfer disabled, or telephony/transfer
    is not configured — escalation still notifies operators in those cases.
    """
    if not settings.voice_sentiment_auto_transfer:
        return False
    if not call_control_id or agent is None:
        return False

    from app.services.ai.tool_executor import create_tool_callback
    from app.services.ai.voice_tools import is_transfer_enabled

    if not is_transfer_enabled(agent):
        log.info("live_sentiment_auto_transfer_skipped", reason="transfer_not_enabled")
        return False

    # Route through the same callback the LLM uses so the auto-transfer still
    # honors the operator's HITL approval gate (auto / pending / blocked)
    # instead of bypassing policy.
    callback = create_tool_callback(
        agent=agent,
        contact_info=contact_info,
        timezone="America/New_York",
        call_control_id=call_control_id,
        log=log,
        workspace_id=workspace_id,
    )
    result = await callback(
        call_control_id,
        "transfer_call",
        {
            "reason": "sustained negative sentiment detected on the live call",
            "intent": "caller appears frustrated/upset",
        },
    )
    transferred = bool(result.get("success") and result.get("transferred"))
    log.info(
        "live_sentiment_auto_transfer_result",
        transferred=transferred,
        mode=result.get("mode"),
        pending_approval=result.get("pending_approval"),
        blocked=result.get("blocked"),
        error=result.get("error"),
    )
    return transferred


def build_live_sentiment_handler(
    *,
    call_id: str,
    workspace_id: uuid.UUID,
    agent: Any,
    contact_info: dict[str, Any] | None,
    log: Any,
) -> Callable[[SentimentUpdate], Awaitable[None]]:
    """Build the async callback the voice agent invokes per scored utterance.

    The returned closure resolves the call's Message id lazily (and caches it),
    persists each update's live signals, and on escalation emits the
    ``live_sentiment_escalation`` event plus operator notification / transfer.
    """
    state: dict[str, Any] = {"message_id": None, "resolved": False}

    async def handle(update: SentimentUpdate) -> None:
        if not state["resolved"]:
            state["message_id"] = await _resolve_message_id(call_id)
            state["resolved"] = True
            if state["message_id"] is None:
                log.warning("live_sentiment_message_not_found", call_id=call_id)

        message_id: uuid.UUID | None = state["message_id"]
        if message_id is not None:
            await _persist_live_signals(message_id, update, log)

        if not update.escalate:
            return

        # This is the event verified via logs.
        log.warning(
            "live_sentiment_escalation",
            call_id=call_id,
            workspace_id=str(workspace_id),
            sentiment=update.sentiment,
            sentiment_score=round(update.score, 4),
            consecutive_negative=update.consecutive_negative,
            turns=update.turns,
            auto_transfer_enabled=settings.voice_sentiment_auto_transfer,
        )

        await _notify_operators(workspace_id, update, contact_info, log)

        transferred = await _maybe_auto_transfer(
            agent=agent,
            contact_info=contact_info,
            call_control_id=call_id,
            workspace_id=workspace_id,
            update=update,
            log=log,
        )
        log.info(
            "live_sentiment_escalation_handled",
            call_id=call_id,
            auto_transferred=transferred,
        )

    return handle
