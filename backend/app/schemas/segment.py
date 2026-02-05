"""Segment schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FilterRule(BaseModel):
    """A single filter rule."""

    field: str
    operator: str
    value: str | int | float | bool | list[str] | list[int] | None = None


class FilterDefinition(BaseModel):
    """Definition of a filter set."""

    logic: str = "and"
    rules: list[FilterRule] = Field(default_factory=list)


class SegmentCreate(BaseModel):
    """Schema for creating a segment."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    definition: FilterDefinition
    is_dynamic: bool = True


class SegmentUpdate(BaseModel):
    """Schema for updating a segment."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    definition: FilterDefinition | None = None
    is_dynamic: bool | None = None


class SegmentResponse(BaseModel):
    """Schema for segment response."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None
    definition: dict[str, Any]
    is_dynamic: bool
    contact_count: int
    last_computed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SegmentListResponse(BaseModel):
    """Schema for segment list response."""

    items: list[SegmentResponse]
    total: int


class SegmentContactsResponse(BaseModel):
    """Schema for segment contacts resolution."""

    ids: list[int]
    total: int
