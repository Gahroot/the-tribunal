"""Contact schemas."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.tag import TagResponse


class ContactCreate(BaseModel):
    """Schema for creating a contact."""

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    email: EmailStr | None = None
    phone_number: str = Field(..., min_length=10, max_length=20)
    company_name: str | None = Field(None, max_length=255)
    address_line1: str | None = Field(None, max_length=255)
    address_line2: str | None = Field(None, max_length=255)
    address_city: str | None = Field(None, max_length=100)
    address_state: str | None = Field(None, max_length=50)
    address_zip: str | None = Field(None, max_length=20)
    status: str = Field(default="new")
    tags: list[str] | None = None
    notes: str | None = None
    source: str | None = None
    important_dates: dict[str, Any] | None = None


class ContactUpdate(BaseModel):
    """Schema for updating a contact."""

    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    email: EmailStr | None = None
    phone_number: str | None = Field(None, min_length=10, max_length=20)
    company_name: str | None = Field(None, max_length=255)
    address_line1: str | None = Field(None, max_length=255)
    address_line2: str | None = Field(None, max_length=255)
    address_city: str | None = Field(None, max_length=100)
    address_state: str | None = Field(None, max_length=50)
    address_zip: str | None = Field(None, max_length=20)
    status: str | None = None
    tags: list[str] | None = None
    notes: str | None = None
    lead_score: int | None = None
    important_dates: dict[str, Any] | None = None


class QualificationSignalDetail(BaseModel):
    """Detail for a single BANT qualification signal."""

    detected: bool = False
    value: str | None = None
    confidence: float = 0.0


class QualificationSignals(BaseModel):
    """Extracted qualification signals from conversations (BANT framework)."""

    budget: QualificationSignalDetail = Field(default_factory=QualificationSignalDetail)
    authority: QualificationSignalDetail = Field(default_factory=QualificationSignalDetail)
    need: QualificationSignalDetail = Field(default_factory=QualificationSignalDetail)
    timeline: QualificationSignalDetail = Field(default_factory=QualificationSignalDetail)
    interest_level: str = "unknown"  # high, medium, low, unknown
    pain_points: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    next_steps: str | None = None
    last_analyzed_at: datetime | None = None
    conversation_count: int = 0


class ContactResponse(BaseModel):
    """Schema for contact response."""

    id: int
    workspace_id: uuid.UUID
    first_name: str
    last_name: str | None
    email: str | None
    phone_number: str
    company_name: str | None
    address_line1: str | None = None
    address_line2: str | None = None
    address_city: str | None = None
    address_state: str | None = None
    address_zip: str | None = None
    status: str
    lead_score: int
    is_qualified: bool
    qualification_signals: QualificationSignals | None
    qualified_at: datetime | None
    tags: list[str] | None
    notes: str | None
    important_dates: dict[str, Any] | None = None
    source: str | None
    source_campaign_id: uuid.UUID | None
    # AI Enrichment fields
    website_url: str | None = None
    linkedin_url: str | None = None
    business_intel: dict[str, Any] | None = None
    enrichment_status: str | None = None
    enriched_at: datetime | None = None
    noshow_count: int = 0
    last_appointment_status: str | None = None
    tag_objects: list[TagResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContactWithConversationResponse(ContactResponse):
    """Contact response with conversation metadata for list views."""

    unread_count: int = 0
    last_message_at: datetime | None = None
    last_message_direction: str | None = None


class BulkStatusUpdateRequest(BaseModel):
    """Request schema for bulk updating contact statuses."""

    ids: list[int]
    status: Literal["new", "contacted", "qualified", "converted", "lost"]


class BulkStatusUpdateResponse(BaseModel):
    """Response schema for bulk status update operation."""

    updated: int
    failed: int
    errors: list[str]


class ContactListResponse(BaseModel):
    """Schema for paginated contact list."""

    items: list[ContactWithConversationResponse]
    total: int
    page: int
    page_size: int
    pages: int


class BulkDeleteRequest(BaseModel):
    """Request schema for bulk contact deletion."""

    ids: list[int]


class BulkDeleteResponse(BaseModel):
    """Response schema for bulk contact deletion."""

    deleted: int
    failed: int
    errors: list[str]


class SendMessageToContactRequest(BaseModel):
    """Request schema for sending a message to a contact."""

    body: str
    from_number: str | None = None  # Optional: specific phone number to send from


class MessageResponse(BaseModel):
    """Response schema for a message."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    direction: str
    channel: str
    body: str
    status: str
    is_ai: bool
    agent_id: uuid.UUID | None
    sent_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContactIdsResponse(BaseModel):
    """Response schema for contact IDs."""

    ids: list[int]
    total: int


class AIToggleRequest(BaseModel):
    """Request schema for toggling AI on a contact's conversation."""

    enabled: bool


class AIToggleResponse(BaseModel):
    """Response schema for AI toggle."""

    ai_enabled: bool
    conversation_id: uuid.UUID


class TimelineItem(BaseModel):
    """A unified timeline item."""

    id: uuid.UUID
    type: str  # "sms", "call", "appointment", "note"
    timestamp: datetime
    direction: str | None = None
    is_ai: bool = False
    content: str
    duration_seconds: int | None = None
    recording_url: str | None = None
    transcript: str | None = None
    status: str | None = None
    booking_outcome: str | None = None
    original_id: uuid.UUID
    original_type: str  # "sms_message", "call_record", "appointment", "note"

    model_config = ConfigDict(from_attributes=True)


class ContactEngagementSummary(BaseModel):
    """Aggregated engagement stats for a single contact."""

    total_messages_sent: int
    total_messages_received: int
    total_calls: int
    total_calls_answered: int
    total_appointments: int
    events_last_7d: int
    events_last_30d: int
    last_activity_at: datetime | None
    channels_used: list[str]


class ImportResult(BaseModel):
    """Result of a CSV import operation."""

    total_rows: int
    successful: int
    failed: int
    skipped_duplicates: int
    errors: list[Any]
    created_contacts: list[ContactResponse]


class CSVPreviewResponse(BaseModel):
    """Response from previewing a CSV file for import."""

    headers: list[str]
    sample_rows: list[dict[str, str]]
    suggested_mapping: dict[str, str | None]
    contact_fields: list[dict[str, Any]]


class QualifyContactResponse(BaseModel):
    """Response from analyzing and qualifying a contact."""

    success: bool
    contact_id: int | None = None
    lead_score: int = 0
    is_qualified: bool = False
    qualification_signals: QualificationSignals | None = None
    has_appointment: bool = False
    response_rate: float = 0.0
    message: str | None = None
    error: str | None = None


class BatchQualifyResponse(BaseModel):
    """Response from batch qualification analysis."""

    success: bool
    analyzed: int = 0
    qualified: int = 0
    errors: int = 0
    contacts: list[dict[str, Any]] = []
    error: str | None = None
