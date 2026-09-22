"""Decision/trace log for autonomously-sent outbound messages.

Every message the AI sales agent sends on its own authority persists one
:class:`MessageTrace` row so an operator can later answer "why did the agent
send that?". The trace links the outbound :class:`~app.models.conversation.Message`
to the prompt/opener version used, the knowledge snippets retrieved, the model
and key sampling params, the prospect/conversation state plus last inbound, and
which autonomy-mandate rule authorized the send.

Append-only and debugging-oriented: a bad message is training data we must be
able to explain, so the row keeps the full system prompt and retrieved passages
rather than just identifiers.
"""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.conversation import Conversation, Message
    from app.models.prompt_version import PromptVersion
    from app.models.workspace import Workspace


class MessageTrace(Base):
    """Explainability record for one autonomously-sent outbound message."""

    __tablename__ = "message_traces"
    __table_args__ = (
        # One trace per message so a debugger can fetch unambiguously by message.
        UniqueConstraint("message_id", name="uq_message_traces_message_id"),
        Index("ix_message_traces_conversation_created_at", "conversation_id", "created_at"),
        Index("ix_message_traces_workspace_created_at", "workspace_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nullable so a trace can be persisted even if the message row could not be
    # resolved; uniquely indexed so each delivered message maps to one trace.
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=True,
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompt_versions.id", ondelete="SET NULL"),
        nullable=True,
    )

    # The exact text the model produced for this send (kept even when message_id
    # is missing, so a failed/blocked send is still explainable).
    generated_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Opener/prompt version snapshot: full system prompt, its fingerprint, and
    # which optional sections were injected (booking instructions, knowledge
    # preamble).
    prompt: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Ranked knowledge passages retrieved for this turn (preamble + on-demand
    # search_knowledge results), each tagged with source title/score.
    knowledge_snippets: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    # Model + key sampling params (model, temperature, max_completion_tokens,
    # tool_choice, timeout).
    model_params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Prospect/conversation state at decision time, including the last inbound.
    conversation_state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Which autonomy-mandate rule authorized the autonomous send, plus any
    # escalation matches detected on the last inbound.
    mandate: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    workspace: Mapped["Workspace"] = relationship("Workspace")
    conversation: Mapped["Conversation"] = relationship("Conversation")
    message: Mapped["Message | None"] = relationship("Message")
    agent: Mapped["Agent | None"] = relationship("Agent")
    prompt_version: Mapped["PromptVersion | None"] = relationship("PromptVersion")

    def __repr__(self) -> str:
        return (
            f"<MessageTrace(id={self.id}, conversation_id={self.conversation_id}, "
            f"message_id={self.message_id})>"
        )
