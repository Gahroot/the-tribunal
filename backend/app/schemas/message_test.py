"""Message test schemas."""

import uuid
from datetime import datetime, time

from pydantic import BaseModel, field_serializer, field_validator

# === Variant Schemas ===


class TestVariantCreate(BaseModel):
    """Schema for creating a test variant."""

    name: str
    message_template: str
    is_control: bool = False
    sort_order: int = 0


class TestVariantUpdate(BaseModel):
    """Schema for updating a test variant."""

    name: str | None = None
    message_template: str | None = None
    is_control: bool | None = None
    sort_order: int | None = None


class TestVariantResponse(BaseModel):
    """Test variant response schema."""

    id: uuid.UUID
    message_test_id: uuid.UUID
    name: str
    message_template: str
    is_control: bool
    sort_order: int
    contacts_assigned: int
    messages_sent: int
    replies_received: int
    contacts_qualified: int
    response_rate: float
    qualification_rate: float
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# === Test Contact Schemas ===


class TestContactAdd(BaseModel):
    """Schema for adding contacts to a message test."""

    contact_ids: list[int]


class TestContactResponse(BaseModel):
    """Test contact response schema."""

    id: uuid.UUID
    message_test_id: uuid.UUID
    contact_id: int
    variant_id: uuid.UUID | None
    conversation_id: uuid.UUID | None
    status: str
    is_qualified: bool
    opted_out: bool
    first_sent_at: datetime | None
    last_reply_at: datetime | None
    variant_assigned_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


# === Message Test Schemas ===


class MessageTestCreate(BaseModel):
    """Schema for creating a message test."""

    name: str
    description: str | None = None
    from_phone_number: str
    use_number_pool: bool = False
    agent_id: uuid.UUID | None = None
    ai_enabled: bool = True
    qualification_criteria: str | None = None
    sending_hours_start: str | None = None  # "09:00"
    sending_hours_end: str | None = None  # "17:00"
    sending_days: list[int] | None = None  # [0,1,2,3,4] = Mon-Fri
    timezone: str = "America/New_York"
    messages_per_minute: int = 10
    # Initial variants (optional, can add separately)
    variants: list[TestVariantCreate] | None = None


class MessageTestUpdate(BaseModel):
    """Schema for updating a message test."""

    name: str | None = None
    description: str | None = None
    from_phone_number: str | None = None
    use_number_pool: bool | None = None
    agent_id: uuid.UUID | None = None
    ai_enabled: bool | None = None
    qualification_criteria: str | None = None
    sending_hours_start: str | None = None
    sending_hours_end: str | None = None
    sending_days: list[int] | None = None
    timezone: str | None = None
    messages_per_minute: int | None = None


class MessageTestResponse(BaseModel):
    """Message test response schema."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    agent_id: uuid.UUID | None
    name: str
    description: str | None
    status: str
    from_phone_number: str
    use_number_pool: bool
    ai_enabled: bool
    qualification_criteria: str | None
    sending_hours_start: str | None
    sending_hours_end: str | None
    sending_days: list[int] | None
    timezone: str
    messages_per_minute: int
    total_contacts: int
    total_variants: int
    messages_sent: int
    replies_received: int
    contacts_qualified: int
    winning_variant_id: uuid.UUID | None
    converted_to_campaign_id: uuid.UUID | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @field_validator("sending_hours_start", "sending_hours_end", mode="before")
    @classmethod
    def validate_sending_hours(cls, v: time | str | None) -> str | None:
        """Convert time objects to string format during validation."""
        if v is None:
            return None
        if isinstance(v, time):
            return v.strftime("%H:%M")
        return v

    @field_serializer("sending_hours_start", "sending_hours_end")
    def serialize_time(self, v: time | str | None) -> str | None:
        """Serialize time to string format."""
        if v is None:
            return None
        if isinstance(v, time):
            return v.strftime("%H:%M")
        return v


class MessageTestWithVariantsResponse(MessageTestResponse):
    """Message test response with variants included."""

    variants: list[TestVariantResponse]


# === Pagination ===


class PaginatedMessageTests(BaseModel):
    """Paginated message tests response."""

    items: list[MessageTestResponse]
    total: int
    page: int
    page_size: int
    pages: int


# === Analytics Schemas ===


class VariantAnalytics(BaseModel):
    """Analytics for a single variant."""

    variant_id: uuid.UUID
    variant_name: str
    is_control: bool
    contacts_assigned: int
    messages_sent: int
    replies_received: int
    contacts_qualified: int
    response_rate: float
    qualification_rate: float


class MessageTestAnalytics(BaseModel):
    """Message test analytics response."""

    test_id: uuid.UUID
    test_name: str
    status: str
    total_contacts: int
    total_variants: int
    messages_sent: int
    replies_received: int
    contacts_qualified: int
    overall_response_rate: float
    overall_qualification_rate: float
    variants: list[VariantAnalytics]
    winning_variant_id: uuid.UUID | None
    statistical_significance: bool  # If we have enough data to declare a winner


# === Action Schemas ===


class SelectWinnerRequest(BaseModel):
    """Request to select a winning variant."""

    variant_id: uuid.UUID


class ConvertToCampaignRequest(BaseModel):
    """Request to convert test to a full campaign."""

    campaign_name: str
    use_winning_message: bool = True
    include_remaining_contacts: bool = True
