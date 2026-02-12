"""Contact schemas."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.tag import TagResponse


class ContactCreate(BaseModel):
    """Schema for creating a contact."""

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    email: EmailStr | None = None
    phone_number: str = Field(..., min_length=10, max_length=20)
    company_name: str | None = Field(None, max_length=255)
    status: str = Field(default="new")
    tags: list[str] | None = None
    notes: str | None = None
    source: str | None = None


class ContactUpdate(BaseModel):
    """Schema for updating a contact."""

    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    email: EmailStr | None = None
    phone_number: str | None = Field(None, min_length=10, max_length=20)
    company_name: str | None = Field(None, max_length=255)
    status: str | None = None
    tags: list[str] | None = None
    notes: str | None = None
    lead_score: int | None = None


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
    status: str
    lead_score: int
    is_qualified: bool
    qualification_signals: QualificationSignals | None
    qualified_at: datetime | None
    tags: list[str] | None
    notes: str | None
    source: str | None
    source_campaign_id: uuid.UUID | None
    # AI Enrichment fields
    website_url: str | None = None
    linkedin_url: str | None = None
    business_intel: dict[str, Any] | None = None
    enrichment_status: str | None = None
    enriched_at: datetime | None = None
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
