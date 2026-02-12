"""Message template schemas for API validation."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MessageTemplateCreate(BaseModel):
    """Schema for creating a message template."""

    name: str = Field(..., min_length=1, max_length=255)
    message_template: str = Field(..., min_length=1)


class MessageTemplateUpdate(BaseModel):
    """Schema for updating a message template."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    message_template: str | None = Field(default=None, min_length=1)


class MessageTemplateResponse(BaseModel):
    """Schema for message template response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    message_template: str
    created_at: datetime
    updated_at: datetime


class PaginatedMessageTemplates(BaseModel):
    """Paginated message templates response."""

    items: list[MessageTemplateResponse]
    total: int
    page: int
    page_size: int
    pages: int
