"""Schemas for the autonomous-message decision/trace log."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class MessageTraceResponse(BaseModel):
    """Explainability record for one autonomously-sent outbound message."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    conversation_id: uuid.UUID
    message_id: uuid.UUID | None
    agent_id: uuid.UUID | None
    prompt_version_id: uuid.UUID | None
    generated_text: str | None
    prompt: dict[str, Any]
    knowledge_snippets: list[dict[str, Any]]
    model_params: dict[str, Any]
    conversation_state: dict[str, Any]
    mandate: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
