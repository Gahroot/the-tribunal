"""Workspace schemas."""

import typing
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.services.autonomy_mandate import normalize_autonomy_mandate


class WorkspaceCreate(BaseModel):
    """Schema for creating a workspace."""

    name: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: str | None = None
    settings: dict[str, typing.Any] = Field(default_factory=dict)


class WorkspaceUpdate(BaseModel):
    """Schema for updating a workspace."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    settings: dict[str, typing.Any] | None = None


class QuietHoursMandate(BaseModel):
    """Daily quiet-hours window for autonomous sends."""

    enabled: bool = True
    timezone: str = Field(default="America/New_York", min_length=1, max_length=100)
    start: str = Field(default="20:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(default="08:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class BatchPackMandate(BaseModel):
    """Batch pack that autonomy may sell without approval."""

    pack_key: str = Field(..., min_length=1, max_length=80)
    label: str = Field(..., min_length=1, max_length=120)
    ad_count: int = Field(..., ge=1, le=100_000)
    price_cents: int = Field(..., ge=0, le=10_000_000)


class EscalationRuleMandate(BaseModel):
    """Rule that hands a buyer to a human instead of continuing autonomously."""

    key: str = Field(..., min_length=1, max_length=80)
    label: str = Field(..., min_length=1, max_length=240)
    keywords: list[str] = Field(default_factory=list)


class OperatorReportMandate(BaseModel):
    """Operator reporting preferences for autonomous outcomes."""

    enabled: bool = True
    channel: Literal["sms", "push", "email"] = "sms"
    phone: str | None = None
    events: list[str] = Field(default_factory=lambda: ["payment_succeeded", "human_escalation"])


class AutonomyMandate(BaseModel):
    """Workspace-level autonomy policy for act-and-report sales execution."""

    version: int = 1
    enabled: bool = True
    posture: Literal["draft_and_wait", "act_and_report"] = "act_and_report"
    auto_send_first_touches: bool = True
    auto_close_batch_packs: bool = True
    default_offer_id: uuid.UUID | None = None
    description: str | None = None
    batch_pack_anchor_key: str = "anchor_500"
    batch_pack_max_price_cents: int = Field(399_700, ge=0, le=10_000_000)
    allowed_batch_packs: list[BatchPackMandate] = Field(default_factory=list)
    daily_send_cap: int = Field(100, ge=1, le=10_000)
    quiet_hours: QuietHoursMandate = Field(default_factory=lambda: QuietHoursMandate())
    escalation_rules: list[EscalationRuleMandate] = Field(default_factory=list)
    operator_report: OperatorReportMandate = Field(default_factory=OperatorReportMandate)

    @field_validator("allowed_batch_packs")
    @classmethod
    def _packs_required(cls, value: list[BatchPackMandate]) -> list[BatchPackMandate]:
        if not value:
            raise ValueError("At least one allowed batch pack is required")
        return value


class AutonomyMandateUpdate(BaseModel):
    """Full replacement payload for a workspace autonomy mandate."""

    mandate: AutonomyMandate


class WorkspaceResponse(BaseModel):
    """Schema for workspace response."""

    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    settings: dict[str, typing.Any]
    autonomy_mandate: AutonomyMandate
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @field_validator("autonomy_mandate", mode="before")
    @classmethod
    def _normalize_autonomy_mandate(cls, value: typing.Any) -> dict[str, typing.Any]:
        return normalize_autonomy_mandate(value if isinstance(value, dict) else None)

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


class UpdateMemberRoleRequest(BaseModel):
    """Request to update a member's role."""

    role: Literal["admin", "member"]


class MemberResponse(BaseModel):
    """Response for member operations."""

    user_id: int
    role: str
    message: str
