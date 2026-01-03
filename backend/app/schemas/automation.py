"""Automation schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AutomationActionSchema(BaseModel):
    """Schema for automation action."""

    type: str = Field(
        ...,
        description="Action type: send_sms, send_email, make_call, add_tag, assign_agent",
    )
    config: dict[str, Any] = Field(
        default_factory=dict, description="Action-specific configuration"
    )


class AutomationCreate(BaseModel):
    """Schema for creating an automation."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    trigger_type: str = Field(default="event", pattern="^(event|schedule|condition)$")
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    actions: list[AutomationActionSchema] = Field(default_factory=list)
    is_active: bool = True


class AutomationUpdate(BaseModel):
    """Schema for updating an automation."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    trigger_type: str | None = Field(default=None, pattern="^(event|schedule|condition)$")
    trigger_config: dict[str, Any] | None = None
    actions: list[AutomationActionSchema] | None = None
    is_active: bool | None = None


class AutomationResponse(BaseModel):
    """Schema for automation response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    description: str | None
    trigger_type: str
    trigger_config: dict[str, Any]
    actions: list[dict[str, Any]]
    is_active: bool
    last_triggered_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PaginatedAutomations(BaseModel):
    """Paginated automations response."""

    items: list[AutomationResponse]
    total: int
    page: int
    page_size: int
    pages: int
