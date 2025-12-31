"""Workspace schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class WorkspaceCreate(BaseModel):
    """Schema for creating a workspace."""

    name: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: str | None = None
    settings: dict = Field(default_factory=dict)


class WorkspaceUpdate(BaseModel):
    """Schema for updating a workspace."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    settings: dict | None = None


class WorkspaceResponse(BaseModel):
    """Schema for workspace response."""

    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    settings: dict
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceMembershipResponse(BaseModel):
    """Schema for workspace membership response."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: int
    role: str
    is_default: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceWithMembership(BaseModel):
    """Schema for workspace with membership info."""

    workspace: WorkspaceResponse
    role: str
    is_default: bool
