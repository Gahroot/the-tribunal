"""Automation schemas."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Trigger identifiers accepted by the automation engine. Combines the legacy
# generic kinds (event/schedule/condition), the polling triggers evaluated
# against contacts, and the event triggers drained from ``automation_events``.
AUTOMATION_TRIGGER_TYPES: tuple[str, ...] = (
    # Generic / legacy kinds
    "event",
    "schedule",
    "condition",
    # Polling triggers (contact-centric)
    "appointment_booked",
    "booking_created",
    "no_show",
    "contact_tagged",
    "never_booked",
    # Event triggers (emitted by services)
    "review_received",
    "review_request_response",
    "opportunity_created",
    "deal_stage_changed",
    "missed_call",
    "roleplay_completed",
    "knowledge_document_uploaded",
)

_TRIGGER_PATTERN = "^(" + "|".join(AUTOMATION_TRIGGER_TYPES) + ")$"


class AutomationActionSchema(BaseModel):
    """Schema for automation action."""

    type: str = Field(
        ...,
        description=(
            "Action type: send_sms (config.message), send_email (config.subject + "
            "config.message), make_call (optional config.agent_id), enroll_campaign "
            "(config.campaign_id), apply_tag/add_tag (config.tag)"
        ),
    )
    config: dict[str, Any] = Field(
        default_factory=dict, description="Action-specific configuration"
    )


class AutomationCreate(BaseModel):
    """Schema for creating an automation."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    trigger_type: str = Field(default="event", pattern=_TRIGGER_PATTERN)
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    actions: list[AutomationActionSchema] = Field(default_factory=list)
    is_active: bool = True


class AutomationUpdate(BaseModel):
    """Schema for updating an automation."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    trigger_type: str | None = Field(default=None, pattern=_TRIGGER_PATTERN)
    trigger_config: dict[str, Any] | None = None
    actions: list[AutomationActionSchema] | None = None
    is_active: bool | None = None


class AutomationConfigIssueSchema(BaseModel):
    """One reason an automation cannot be activated yet."""

    code: str
    field: str
    message: str


class AutomationExecutionSummary(BaseModel):
    """Outcome of the most recent automation run.

    ``status`` is the stored execution status: ``pending`` (running),
    ``completed`` (succeeded), or ``failed`` (``error`` says how to fix it).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    error: str | None
    contact_id: int | None
    created_at: datetime
    executed_at: datetime | None


class AutomationResponse(BaseModel):
    """Schema for automation response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    description: str | None
    trigger_type: str
    trigger_config: dict[str, Any]
    actions: list[dict[str, Any]]
    is_active: bool
    last_triggered_at: datetime | None
    created_at: datetime
    updated_at: datetime
    # Readiness: "ready" when the worker can execute every part of the
    # automation, otherwise "incomplete" with the blocking ``config_issues``.
    readiness: Literal["ready", "incomplete"] = "ready"
    config_issues: list[AutomationConfigIssueSchema] = Field(default_factory=list)
    last_execution: AutomationExecutionSummary | None = None


class PaginatedAutomations(BaseModel):
    """Paginated automations response."""

    items: list[AutomationResponse]
    total: int
    page: int
    page_size: int
    pages: int


class AutomationStatsResponse(BaseModel):
    """Automation statistics response."""

    total: int
    active: int
    triggered_today: int
