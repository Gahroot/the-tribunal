"""Workspace invitation schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class InvitationCreate(BaseModel):
    """Schema for creating an invitation."""

    email: EmailStr
    role: Literal["admin", "member"] = Field(
        default="member",
        description="Role to assign when invitation is accepted",
    )
    message: str | None = Field(
        default=None,
        max_length=500,
        description="Optional personal message to include in the invitation email",
    )


class InvitationResponse(BaseModel):
    """Schema for invitation response."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    email: str
    role: str
    status: str
    message: str | None
    invited_by_email: str | None = None
    invited_by_name: str | None = None
    expires_at: datetime
    created_at: datetime
    accepted_at: datetime | None = None

    model_config = {"from_attributes": True}


class InvitationPublicResponse(BaseModel):
    """Schema for public invitation details (token-based lookup)."""

    workspace_name: str
    workspace_slug: str
    email: str
    role: str
    invited_by_name: str | None = None
    expires_at: datetime
    is_expired: bool
    is_valid: bool


class InvitationAcceptRequest(BaseModel):
    """Schema for accepting an invitation."""

    # If user is not logged in, they need to provide registration details
    # If logged in, no additional data needed
    pass


class InvitationAcceptResponse(BaseModel):
    """Schema for invitation accept response."""

    success: bool
    message: str
    workspace_id: uuid.UUID | None = None
    workspace_slug: str | None = None
