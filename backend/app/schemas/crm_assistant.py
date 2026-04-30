"""CRM assistant schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AssistantChatRequest(BaseModel):
    """Request to send a message to the CRM assistant."""

    message: str


class ActionSummary(BaseModel):
    """Summary of a tool action taken by the assistant."""

    tool_name: str
    success: bool
    summary: str


class AssistantChatResponse(BaseModel):
    """Response from the CRM assistant."""

    response: str
    actions_taken: list[ActionSummary] = []


class AssistantMessageResponse(BaseModel):
    """A single message in an assistant conversation."""

    id: str
    role: str
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssistantConversationResponse(BaseModel):
    """Full assistant conversation with messages."""

    id: str
    messages: list[AssistantMessageResponse]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
