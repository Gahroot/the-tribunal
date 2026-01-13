"""Integration credential schemas."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

IntegrationType = Literal["calcom", "telnyx", "openai", "sendgrid"]


class IntegrationCredentialsBase(BaseModel):
    """Base schema for integration credentials."""

    api_key: str = Field(..., min_length=1, description="API key for the integration")


class CalcomCredentials(IntegrationCredentialsBase):
    """Cal.com specific credentials."""

    event_type_id: str | None = Field(None, description="Default event type ID for bookings")


class TelnyxCredentials(IntegrationCredentialsBase):
    """Telnyx specific credentials."""

    messaging_profile_id: str | None = Field(None, description="Messaging profile ID")
    phone_number: str | None = Field(None, description="Default phone number")


class OpenAICredentials(IntegrationCredentialsBase):
    """OpenAI specific credentials."""

    organization_id: str | None = Field(None, description="OpenAI organization ID")


class SendGridCredentials(IntegrationCredentialsBase):
    """SendGrid specific credentials."""

    from_email: str | None = Field(None, description="Default sender email address")
    from_name: str | None = Field(None, description="Default sender name")


class IntegrationCreate(BaseModel):
    """Schema for creating/updating an integration."""

    integration_type: IntegrationType
    credentials: dict[str, Any] = Field(..., description="Integration-specific credentials")
    is_active: bool = Field(default=True)


class IntegrationUpdate(BaseModel):
    """Schema for updating an integration."""

    credentials: dict[str, Any] | None = Field(None, description="Integration-specific credentials")
    is_active: bool | None = None


class IntegrationResponse(BaseModel):
    """Schema for integration response."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    integration_type: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    # Note: credentials are not returned in responses for security

    model_config = {"from_attributes": True}


class IntegrationWithMaskedCredentials(IntegrationResponse):
    """Schema for integration response with masked credentials."""

    masked_credentials: dict[str, str] = Field(
        default_factory=dict,
        description="Masked credential keys (e.g., 'sk_****1234')",
    )


class IntegrationTestResult(BaseModel):
    """Schema for integration test result."""

    success: bool
    message: str
    details: dict[str, Any] | None = None
