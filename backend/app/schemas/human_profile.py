"""Human profile schemas for HITL system endpoints."""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict


class HumanProfileResponse(BaseModel):
    """Schema for human profile response."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    agent_id: uuid.UUID
    display_name: str
    role_title: str | None
    phone_number: str | None
    email: str | None
    timezone: str
    bio: str | None
    communication_preferences: dict[str, Any]
    action_policies: dict[str, Any]
    default_policy: str
    auto_approve_timeout_minutes: int
    auto_reject_timeout_minutes: int
    is_active: bool
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)


class HumanProfileCreate(BaseModel):
    """Schema for creating a human profile."""

    display_name: str
    role_title: str | None = None
    phone_number: str | None = None
    email: str | None = None
    timezone: str = "America/New_York"
    bio: str | None = None
    communication_preferences: dict[str, Any] = {}
    action_policies: dict[str, Any] = {}
    default_policy: str = "ask"
    auto_approve_timeout_minutes: int = 0
    auto_reject_timeout_minutes: int = 1440
    is_active: bool = True


class HumanProfileUpdate(BaseModel):
    """Schema for updating a human profile."""

    display_name: str | None = None
    role_title: str | None = None
    phone_number: str | None = None
    email: str | None = None
    timezone: str | None = None
    bio: str | None = None
    communication_preferences: dict[str, Any] | None = None
    action_policies: dict[str, Any] | None = None
    default_policy: str | None = None
    auto_approve_timeout_minutes: int | None = None
    auto_reject_timeout_minutes: int | None = None
    is_active: bool | None = None
