"""Conversation and message schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class MessageCreate(BaseModel):
    """Schema for sending a message."""

    body: str


class MessageResponse(BaseModel):
    """Message response schema."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    direction: str
    channel: str
    body: str
    status: str
    is_ai: bool
    agent_id: uuid.UUID | None
    booking_outcome: str | None = None
    sent_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InboxMessageResponse(MessageResponse):
    """Retain call playback/transcript metadata in the exact-thread inbox."""

    duration_seconds: int | None
    recording_url: str | None
    transcript: str | None


class ConversationResponse(BaseModel):
    """Conversation response schema."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    contact_id: int | None
    workspace_phone: str
    contact_phone: str
    status: str
    channel: str
    assigned_agent_id: uuid.UUID | None
    ai_enabled: bool
    ai_paused: bool
    unread_count: int
    last_message_preview: str | None
    last_message_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationWithMessages(ConversationResponse):
    """Conversation with messages."""

    messages: list[MessageResponse]


class PaginatedConversations(BaseModel):
    """Paginated conversations response."""

    items: list[ConversationResponse]
    total: int
    page: int
    page_size: int
    pages: int


InboxView = Literal["all", "waiting", "hot"]


class InboxSearch(BaseModel):
    """Body-based discovery keeps operator search text out of access-log URLs."""

    view: InboxView = "all"
    q: str = Field("", max_length=200)
    page: int = Field(1, ge=1, le=100000)
    page_size: int = Field(50, ge=1, le=100)


class InboxContactSummary(BaseModel):
    """Only the contact fields needed to render an inbox row."""

    id: int
    first_name: str
    last_name: str | None
    avatar_url: str | None
    status: str
    lead_score: int

    model_config = ConfigDict(from_attributes=True)


class InboxConversationResponse(ConversationResponse):
    """Read-only conversation summary, independent of campaign synchronization."""

    last_message_direction: str | None
    needs_human_reply: bool
    contact: InboxContactSummary | None


class InboxCounts(BaseModel):
    all: int
    waiting: int
    hot: int


class PaginatedInbox(BaseModel):
    items: list[InboxConversationResponse]
    counts: InboxCounts
    total: int
    page: int
    page_size: int
    pages: int


class MarkConversationRead(BaseModel):
    """Acknowledge only the message snapshot actually displayed to the operator."""

    last_message_at: AwareDatetime | None
    unread_count: int = Field(ge=0)


class MarkConversationReadResponse(BaseModel):
    marked_read: bool


class AIToggle(BaseModel):
    """AI toggle request."""

    enabled: bool


class AgentAssign(BaseModel):
    """Agent assignment request."""

    agent_id: uuid.UUID | None


class FollowupSettingsUpdate(BaseModel):
    """Schema for updating follow-up settings."""

    enabled: bool | None = None
    delay_hours: int | None = Field(None, ge=1, le=168)  # 1 hour to 1 week
    max_count: int | None = Field(None, ge=1, le=10)


class FollowupSettingsResponse(BaseModel):
    """Follow-up settings and status response."""

    enabled: bool
    delay_hours: int
    max_count: int
    count_sent: int
    next_followup_at: datetime | None
    last_followup_at: datetime | None


class FollowupGenerateRequest(BaseModel):
    """Request for generating a follow-up message."""

    custom_instructions: str | None = None


class FollowupGenerateResponse(BaseModel):
    """Response with generated follow-up message."""

    message: str
    conversation_id: str


class FollowupSendRequest(BaseModel):
    """Request for sending a follow-up message."""

    message: str | None = None  # If not provided, will generate one
    custom_instructions: str | None = None


class FollowupSendResponse(BaseModel):
    """Response after sending a follow-up."""

    success: bool
    message_id: str | None
    message_body: str
