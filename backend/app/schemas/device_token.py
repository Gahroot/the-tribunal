"""Device token schemas for push notification registration."""

from pydantic import BaseModel


class RegisterTokenRequest(BaseModel):
    """Schema for registering an Expo push token."""

    expo_push_token: str
    device_name: str | None = None
    platform: str | None = None


class RegisterTokenResponse(BaseModel):
    """Schema for token registration response."""

    id: str
    expo_push_token: str
    device_name: str | None
    platform: str | None
