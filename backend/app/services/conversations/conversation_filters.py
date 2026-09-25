"""Shared conversation predicates for the inbox and Today queue."""

import uuid

from sqlalchemy import ColumnElement

from app.models.conversation import Conversation, ConversationStatus


def human_reply_needed_filters(workspace_id: uuid.UUID) -> tuple[ColumnElement[bool], ...]:
    """Unread is attention metadata, not a proxy for unfinished human work."""
    return (
        Conversation.workspace_id == workspace_id,
        Conversation.status == ConversationStatus.ACTIVE,
        Conversation.last_message_direction == "inbound",
        Conversation.ai_paused.is_(True) | Conversation.ai_enabled.is_(False),
    )
