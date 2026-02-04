"""Pydantic schemas for CallOutcome."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CallOutcomeCreate(BaseModel):
    """Schema for creating a call outcome."""

    outcome_type: str = Field(..., description="Call outcome type")
    signals: dict[str, Any] = Field(default_factory=dict)
    classified_by: str = "hangup_cause"
    classification_confidence: float | None = Field(None, ge=0.0, le=1.0)
    raw_hangup_cause: str | None = None


class CallOutcomeUpdate(BaseModel):
    """Schema for updating/reclassifying a call outcome."""

    outcome_type: str | None = None
    signals: dict[str, Any] | None = None
    classified_by: str | None = None
    classification_confidence: float | None = Field(None, ge=0.0, le=1.0)


class CallOutcomeResponse(BaseModel):
    """Schema for call outcome response."""

    id: uuid.UUID
    message_id: uuid.UUID
    prompt_version_id: uuid.UUID | None
    outcome_type: str
    signals: dict[str, Any]
    classified_by: str
    classification_confidence: float | None
    raw_hangup_cause: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CallOutcomeWithContextResponse(CallOutcomeResponse):
    """Call outcome response with additional context."""

    # Message context
    call_duration_seconds: int | None = None
    call_direction: str | None = None
    booking_outcome: str | None = None

    # Prompt version context
    prompt_version_number: int | None = None
    prompt_is_baseline: bool | None = None
