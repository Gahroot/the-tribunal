"""Contact schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class ContactCreate(BaseModel):
    """Schema for creating a contact."""

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    email: EmailStr | None = None
    phone_number: str = Field(..., min_length=10, max_length=20)
    company_name: str | None = Field(None, max_length=255)
    status: str = Field(default="new")
    tags: list[str] | None = None
    notes: str | None = None
    source: str | None = None


class ContactUpdate(BaseModel):
    """Schema for updating a contact."""

    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    email: EmailStr | None = None
    phone_number: str | None = Field(None, min_length=10, max_length=20)
    company_name: str | None = Field(None, max_length=255)
    status: str | None = None
    tags: list[str] | None = None
    notes: str | None = None
    lead_score: int | None = None


class ContactResponse(BaseModel):
    """Schema for contact response."""

    id: int
    workspace_id: uuid.UUID
    first_name: str
    last_name: str | None
    email: str | None
    phone_number: str
    company_name: str | None
    status: str
    lead_score: int
    tags: list[str] | None
    notes: str | None
    source: str | None
    source_campaign_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContactListResponse(BaseModel):
    """Schema for paginated contact list."""

    items: list[ContactResponse]
    total: int
    page: int
    page_size: int
    pages: int
