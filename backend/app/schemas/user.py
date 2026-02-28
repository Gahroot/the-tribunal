"""User schemas."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    """Schema for creating a user."""

    email: EmailStr
    password: str
    full_name: str | None = None


class UserResponse(BaseModel):
    """Schema for user response."""

    id: int
    email: str
    full_name: str | None
    is_active: bool
    created_at: datetime


class UserWithWorkspace(UserResponse):
    """Schema for user response with workspace info."""

    default_workspace_id: str | None = None


class Token(BaseModel):
    """Schema for JWT token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request."""

    refresh_token: str


class TokenPayload(BaseModel):
    """Schema for JWT token payload."""

    sub: int | None = None


# Settings schemas
class UserProfileResponse(BaseModel):
    """Schema for user profile response."""

    id: int
    email: str
    full_name: str | None
    phone_number: str | None
    timezone: str
    created_at: datetime


class UserProfileUpdate(BaseModel):
    """Schema for updating user profile."""

    full_name: str | None = None
    phone_number: str | None = None
    timezone: str | None = None


class NotificationSettings(BaseModel):
    """Schema for notification settings."""

    notification_email: bool
    notification_sms: bool
    notification_push: bool
    notification_push_calls: bool
    notification_push_messages: bool
    notification_push_voicemail: bool


class NotificationSettingsUpdate(BaseModel):
    """Schema for updating notification settings."""

    notification_email: bool | None = None
    notification_sms: bool | None = None
    notification_push: bool | None = None
    notification_push_calls: bool | None = None
    notification_push_messages: bool | None = None
    notification_push_voicemail: bool | None = None


class IntegrationStatus(BaseModel):
    """Schema for integration status."""

    integration_type: str
    is_connected: bool
    display_name: str
    description: str


class IntegrationsResponse(BaseModel):
    """Schema for workspace integrations response."""

    integrations: list[IntegrationStatus]


class TeamMemberResponse(BaseModel):
    """Schema for team member response."""

    id: int
    email: str
    full_name: str | None
    role: str
    created_at: datetime


# Business Hours schemas
class DaySchedule(BaseModel):
    """Schema for a single day's schedule."""

    enabled: bool
    open: str
    close: str


class BusinessHoursSettings(BaseModel):
    """Schema for business hours settings."""

    is_24_7: bool = False
    schedule: dict[str, DaySchedule] = {}


class BusinessHoursUpdate(BaseModel):
    """Schema for updating business hours."""

    is_24_7: bool | None = None
    schedule: dict[str, DaySchedule] | None = None


# Call Forwarding schemas
class CallForwardingSettings(BaseModel):
    """Schema for call forwarding settings."""

    enabled: bool = False
    forward_to: str | None = None
    mode: str = "no_answer"


class CallForwardingUpdate(BaseModel):
    """Schema for updating call forwarding."""

    enabled: bool | None = None
    forward_to: str | None = None
    mode: str | None = None


# Change Password schema
class ChangePasswordRequest(BaseModel):
    """Schema for changing password."""

    current_password: str
    new_password: str = Field(..., min_length=8)
