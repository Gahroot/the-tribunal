"""User schemas."""

from datetime import datetime

from pydantic import BaseModel, EmailStr


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
    token_type: str = "bearer"


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


class NotificationSettingsUpdate(BaseModel):
    """Schema for updating notification settings."""

    notification_email: bool | None = None
    notification_sms: bool | None = None
    notification_push: bool | None = None


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
