"""Embed API schemas for embeddable agent widgets."""

from pydantic import BaseModel, field_validator


class EmbedConfigResponse(BaseModel):
    """Public configuration for embed widget."""

    public_id: str
    name: str
    greeting_message: str | None
    button_text: str
    theme: str
    position: str
    primary_color: str
    language: str
    voice: str
    channel_mode: str


class TokenRequest(BaseModel):
    """Request for ephemeral token."""

    mode: str = "voice"  # voice or chat


class TokenResponse(BaseModel):
    """Ephemeral token response for WebRTC connection."""

    client_secret: dict[str, str]
    agent: dict[str, str | None]
    model: str
    tools: list[dict[str, object]]


class ChatRequest(BaseModel):
    """Chat message request."""

    message: str
    conversation_history: list[dict[str, str]] = []


class ChatResponse(BaseModel):
    """Chat message response."""

    response: str
    tool_calls: list[dict[str, object]] = []


class ToolCallRequest(BaseModel):
    """Tool call execution request."""

    tool_name: str
    arguments: dict[str, object]


class TranscriptRequest(BaseModel):
    """Transcript save request."""

    session_id: str
    transcript: str
    duration_seconds: int


class EmbedPhoneRequest(BaseModel):
    """Request for embed call/text endpoints."""

    phone_number: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Validate and normalize phone number to E.164 format."""
        digits = "".join(c for c in v if c.isdigit())
        if len(digits) == 10:
            return f"+1{digits}"
        elif len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        else:
            raise ValueError("Phone number must be a valid US number (10 digits)")
