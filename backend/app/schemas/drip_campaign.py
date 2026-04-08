"""Pydantic schemas for drip campaign API."""

import uuid
from datetime import datetime, time
from typing import Any

from pydantic import BaseModel, Field


class DripStepSchema(BaseModel):
    """A single step in a drip sequence."""

    step: int
    delay_days: int = Field(ge=0)
    message: str = Field(min_length=1, max_length=640)
    type: str = Field(max_length=50)


class DripCampaignCreate(BaseModel):
    """Request to create a drip campaign."""

    name: str = Field(max_length=255)
    description: str | None = None
    agent_id: uuid.UUID | None = None
    from_phone_number: str
    sequence_steps: list[DripStepSchema]
    sending_hours_start: time | None = None
    sending_hours_end: time | None = None
    sending_days: list[int] | None = None
    timezone: str = "America/New_York"
    messages_per_minute: int = 10
    auto_start: bool = False


class DripCampaignResponse(BaseModel):
    """Response for a drip campaign."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    agent_id: uuid.UUID | None
    name: str
    description: str | None
    status: str
    from_phone_number: str
    sequence_steps: list[dict[str, Any]]
    sending_hours_start: time | None
    sending_hours_end: time | None
    sending_days: list[int] | None
    timezone: str
    messages_per_minute: int
    total_enrolled: int
    total_completed: int
    total_responded: int
    total_cancelled: int
    total_messages_sent: int
    total_appointments_booked: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DripEnrollmentResponse(BaseModel):
    """Response for a drip enrollment."""

    id: uuid.UUID
    drip_campaign_id: uuid.UUID
    contact_id: int
    status: str
    current_step: int
    next_step_at: datetime | None
    response_category: str | None
    cancel_reason: str | None
    messages_sent: int
    messages_received: int
    last_sent_at: datetime | None
    last_reply_at: datetime | None
    enrolled_at: datetime

    model_config = {"from_attributes": True}


class DripCampaignStats(BaseModel):
    """Aggregated stats for a drip campaign."""

    total_enrolled: int
    active: int
    responded: int
    completed: int
    cancelled: int
    messages_sent: int
    appointments_booked: int
    response_rate: float
    completion_rate: float


class EnrollContactsRequest(BaseModel):
    """Request to enroll contacts in a drip campaign."""

    contact_ids: list[int]
