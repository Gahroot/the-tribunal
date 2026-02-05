"""Tag schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TagCreate(BaseModel):
    """Schema for creating a tag."""

    name: str = Field(..., min_length=1, max_length=100)
    color: str = Field(default="#6366f1", pattern=r"^#[0-9a-fA-F]{6}$")


class TagUpdate(BaseModel):
    """Schema for updating a tag."""

    name: str | None = Field(None, min_length=1, max_length=100)
    color: str | None = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")


class TagResponse(BaseModel):
    """Schema for tag response."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    color: str
    contact_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TagListResponse(BaseModel):
    """Schema for tag list response."""

    items: list[TagResponse]
    total: int


class BulkTagRequest(BaseModel):
    """Schema for bulk adding/removing tags on contacts."""

    contact_ids: list[int] = Field(..., min_length=1)
    add_tag_ids: list[uuid.UUID] = Field(default_factory=list)
    remove_tag_ids: list[uuid.UUID] = Field(default_factory=list)


class BulkTagResponse(BaseModel):
    """Response for bulk tag operation."""

    updated: int
    errors: list[str] = Field(default_factory=list)
