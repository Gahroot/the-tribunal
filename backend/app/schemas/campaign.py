"""Campaign schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class CampaignCreate(BaseModel):
    """Schema for creating a campaign."""

    name: str
    agent_id: uuid.UUID | None = None
    from_phone_number: str
    initial_message: str
    ai_enabled: bool = True
    qualification_criteria: str | None = None
    scheduled_start: datetime | None = None
    sending_hours_start: str | None = None  # "09:00"
    sending_hours_end: str | None = None  # "17:00"
    sending_days: list[int] | None = None  # [0,1,2,3,4] = Mon-Fri
    timezone: str = "America/New_York"
    messages_per_minute: int = 10
    follow_up_enabled: bool = False
    follow_up_delay_hours: int = 24
    follow_up_message: str | None = None
    max_follow_ups: int = 2


class CampaignUpdate(BaseModel):
    """Schema for updating a campaign."""

    name: str | None = None
    agent_id: uuid.UUID | None = None
    initial_message: str | None = None
    ai_enabled: bool | None = None
    qualification_criteria: str | None = None
    scheduled_start: datetime | None = None
    sending_hours_start: str | None = None
    sending_hours_end: str | None = None
    sending_days: list[int] | None = None
    timezone: str | None = None
    messages_per_minute: int | None = None
    follow_up_enabled: bool | None = None
    follow_up_delay_hours: int | None = None
    follow_up_message: str | None = None
    max_follow_ups: int | None = None


class CampaignResponse(BaseModel):
    """Campaign response schema."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    agent_id: uuid.UUID | None
    name: str
    status: str
    from_phone_number: str
    initial_message: str
    ai_enabled: bool
    qualification_criteria: str | None
    scheduled_start: datetime | None
    sending_hours_start: str | None
    sending_hours_end: str | None
    sending_days: list[int] | None
    timezone: str
    messages_per_minute: int
    follow_up_enabled: bool
    follow_up_delay_hours: int
    follow_up_message: str | None
    max_follow_ups: int
    total_contacts: int
    messages_sent: int
    replies_received: int
    contacts_qualified: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CampaignContactAdd(BaseModel):
    """Schema for adding contacts to a campaign."""

    contact_ids: list[int]


class CampaignContactResponse(BaseModel):
    """Campaign contact response schema."""

    id: uuid.UUID
    campaign_id: uuid.UUID
    contact_id: int
    conversation_id: uuid.UUID | None
    status: str
    messages_sent: int
    is_qualified: bool
    opted_out: bool
    created_at: datetime

    class Config:
        from_attributes = True


class PaginatedCampaigns(BaseModel):
    """Paginated campaigns response."""

    items: list[CampaignResponse]
    total: int
    page: int
    page_size: int
    pages: int


class CampaignAnalytics(BaseModel):
    """Campaign analytics response."""

    total_contacts: int
    messages_sent: int
    messages_delivered: int
    messages_failed: int
    replies_received: int
    contacts_qualified: int
    contacts_opted_out: int
    reply_rate: float
    qualification_rate: float
