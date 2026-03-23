"""API Key schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class APIKeyCreate(BaseModel):
    """Schema for creating an API key."""

    name: str = Field(..., min_length=1, max_length=100)
    expires_in_days: int | None = Field(None, ge=1, le=365)


class APIKeyResponse(BaseModel):
    """Schema for API key response (redacted)."""

    id: uuid.UUID
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: datetime | None
    expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class APIKeyCreated(BaseModel):
    """Schema returned only on create (contains plaintext key)."""

    id: uuid.UUID
    name: str
    key: str
    key_prefix: str
