"""Lead Source schemas."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class LeadSourceCreate(BaseModel):
    """Schema for creating a lead source."""

    name: str = Field(..., min_length=1, max_length=200)
    allowed_domains: list[str] = Field(default_factory=list)
    action: Literal["collect", "auto_text", "auto_call", "enroll_campaign"] = "collect"
    action_config: dict[str, Any] = Field(default_factory=dict)


class LeadSourceUpdate(BaseModel):
    """Schema for updating a lead source."""

    name: str | None = Field(None, min_length=1, max_length=200)
    allowed_domains: list[str] | None = None
    enabled: bool | None = None
    action: Literal["collect", "auto_text", "auto_call", "enroll_campaign"] | None = None
    action_config: dict[str, Any] | None = None


class LeadSourceResponse(BaseModel):
    """Schema for lead source response."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    public_key: str
    allowed_domains: list[str]
    enabled: bool
    action: str
    action_config: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    endpoint_url: str = ""

    model_config = {"from_attributes": True}


class LeadSubmitRequest(BaseModel):
    """Public-facing lead submission request."""

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    email: EmailStr | None = None
    phone_number: str = Field(..., min_length=10, max_length=20)
    company_name: str | None = Field(None, max_length=255)
    notes: str | None = None
    source_detail: str | None = Field(None, max_length=200)

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
            msg = "Phone number must be a valid US number (10 digits)"
            raise ValueError(msg)

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, v: str) -> str:
        """Validate first name is not empty."""
        if not v or not v.strip():
            msg = "First name is required"
            raise ValueError(msg)
        return v.strip()


class LeadSubmitResponse(BaseModel):
    """Response from public lead submission."""

    success: bool
    message: str
