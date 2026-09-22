"""Build and persist decision/trace records for autonomous outbound messages.

The :class:`OutboundTraceDraft` is filled in while the AI responder generates a
reply (prompt, knowledge, model params, generated text). The caller then snapshots
the prospect/conversation state and the authorizing mandate rule and hands the
draft to :class:`MessageTraceService`, which links it to the delivered
:class:`~app.models.conversation.Message` and writes one :class:`MessageTrace` row.

Read helpers fetch a trace by message (debug "why this message?") or list every
trace for a conversation, both workspace-scoped.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message
from app.models.message_trace import MessageTrace
from app.services.autonomy_mandate import escalation_matches, normalize_autonomy_mandate

logger = structlog.get_logger()

# Cap stored passage content so a wide retrieval can't bloat the trace row.
_MAX_SNIPPETS = 20
_MAX_SNIPPET_CHARS = 2000


@dataclass(slots=True)
class OutboundTraceDraft:
    """Mutable accumulator for one autonomous send's trace, filled during generation."""

    workspace_id: uuid.UUID
    conversation_id: uuid.UUID
    agent_id: uuid.UUID | None = None
    prompt_version_id: uuid.UUID | None = None
    generated_text: str | None = None
    prompt: dict[str, Any] = field(default_factory=dict)
    knowledge_snippets: list[dict[str, Any]] = field(default_factory=list)
    model_params: dict[str, Any] = field(default_factory=dict)
    conversation_state: dict[str, Any] = field(default_factory=dict)
    mandate: dict[str, Any] = field(default_factory=dict)

    def set_model_params(
        self,
        *,
        model: str,
        temperature: float | None = None,
        max_completion_tokens: int | None = None,
        tool_choice: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        """Record the model and the key sampling params used for the send."""
        self.model_params = {
            "model": model,
            "temperature": temperature,
            "max_completion_tokens": max_completion_tokens,
            "tool_choice": tool_choice,
            "timeout_seconds": timeout_seconds,
        }

    def set_prompt(
        self,
        *,
        system_prompt: str,
        booking_instructions_included: bool = False,
        knowledge_preamble_included: bool = False,
    ) -> None:
        """Record the exact opener/system prompt sent and which sections were injected."""
        fingerprint = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()
        self.prompt = {
            "system_prompt": system_prompt,
            "system_prompt_sha256": fingerprint,
            "system_prompt_chars": len(system_prompt),
            "booking_instructions_included": booking_instructions_included,
            "knowledge_preamble_included": knowledge_preamble_included,
        }

    def add_knowledge_passages(
        self,
        passages: Sequence[Mapping[str, Any]],
        *,
        query: str | None = None,
        source: str = "search_knowledge",
    ) -> None:
        """Append retrieved knowledge passages to the trace (deduped/truncated)."""
        for passage in passages:
            if len(self.knowledge_snippets) >= _MAX_SNIPPETS:
                break
            content = str(passage.get("content") or "")
            self.knowledge_snippets.append(
                {
                    "source": source,
                    "query": query,
                    "title": passage.get("title"),
                    "score": passage.get("score"),
                    "content": content[:_MAX_SNIPPET_CHARS],
                }
            )


def build_mandate_authorization(
    mandate: Mapping[str, Any] | None,
    *,
    last_inbound_body: str | None,
    action: str = "conversation_reply",
) -> dict[str, Any]:
    """Describe which autonomy-mandate rule authorized an autonomous send.

    For a conversational reply (objection-handle / anchor-close), the
    workspace's ``act_and_report`` mandate is the authorizing rule. Escalation
    keyword matches on the last inbound are recorded too, so a missed escalation
    (buyer asked for add-ons beyond the batch) is debuggable from the trace.
    """
    policy = normalize_autonomy_mandate(mandate)
    matches = escalation_matches(mandate, last_inbound_body or "")
    enabled = bool(policy.get("enabled", True))
    return {
        "source": "autonomy_mandate",
        "version": policy.get("version"),
        "enabled": enabled,
        "posture": policy.get("posture"),
        "authorized_rule": (
            f"{policy.get('posture', 'act_and_report')}.{action}" if enabled else "disabled"
        ),
        "auto_send_first_touches": policy.get("auto_send_first_touches"),
        "auto_close_batch_packs": policy.get("auto_close_batch_packs"),
        "requires_escalation": bool(matches),
        "escalation_matches": [
            {"key": rule.get("key"), "label": rule.get("label")} for rule in matches
        ],
    }


def build_conversation_state(
    conversation: Conversation,
    *,
    last_inbound: Message | None,
    message_count: int | None = None,
) -> dict[str, Any]:
    """Snapshot the prospect/conversation state and last inbound at decision time."""
    last_inbound_payload: dict[str, Any] | None = None
    if last_inbound is not None:
        last_inbound_payload = {
            "message_id": str(last_inbound.id),
            "body": last_inbound.body,
            "created_at": last_inbound.created_at.isoformat() if last_inbound.created_at else None,
        }
    return {
        "status": getattr(conversation.status, "value", conversation.status),
        "channel": conversation.channel,
        "ai_enabled": conversation.ai_enabled,
        "ai_paused": conversation.ai_paused,
        "assigned_agent_id": str(conversation.assigned_agent_id)
        if conversation.assigned_agent_id
        else None,
        "contact_id": conversation.contact_id,
        "followup_count_sent": conversation.followup_count_sent,
        "message_count": message_count,
        "last_inbound": last_inbound_payload,
    }


class MessageTraceService:
    """Persist and read decision/trace records for autonomous outbound messages."""

    async def record(
        self,
        db: AsyncSession,
        *,
        draft: OutboundTraceDraft,
        message: Message | None,
    ) -> MessageTrace:
        """Persist a trace row linking the draft to the delivered message.

        Flushes (does not commit) so the caller controls the transaction
        boundary alongside the message it just sent.
        """
        trace = MessageTrace(
            workspace_id=draft.workspace_id,
            conversation_id=draft.conversation_id,
            message_id=message.id if message is not None else None,
            agent_id=draft.agent_id,
            prompt_version_id=draft.prompt_version_id,
            generated_text=draft.generated_text,
            prompt=draft.prompt,
            knowledge_snippets=draft.knowledge_snippets,
            model_params=draft.model_params,
            conversation_state=draft.conversation_state,
            mandate=draft.mandate,
        )
        db.add(trace)
        await db.flush()
        logger.info(
            "message_trace_recorded",
            trace_id=str(trace.id),
            conversation_id=str(draft.conversation_id),
            message_id=str(message.id) if message is not None else None,
            knowledge_snippet_count=len(draft.knowledge_snippets),
            requires_escalation=draft.mandate.get("requires_escalation"),
        )
        return trace

    async def get_by_message(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        message_id: uuid.UUID,
    ) -> MessageTrace | None:
        """Return the trace for a message within a workspace, or None."""
        result = await db.execute(
            select(MessageTrace).where(
                MessageTrace.workspace_id == workspace_id,
                MessageTrace.message_id == message_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_conversation(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        limit: int = 100,
    ) -> list[MessageTrace]:
        """Return traces for a conversation (newest first), workspace-scoped."""
        result = await db.execute(
            select(MessageTrace)
            .where(
                MessageTrace.workspace_id == workspace_id,
                MessageTrace.conversation_id == conversation_id,
            )
            .order_by(MessageTrace.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


message_trace_service = MessageTraceService()

__all__ = [
    "MessageTraceService",
    "OutboundTraceDraft",
    "build_conversation_state",
    "build_mandate_authorization",
    "message_trace_service",
]
