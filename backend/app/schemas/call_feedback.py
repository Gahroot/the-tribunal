"""Pydantic schemas for CallFeedback."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CallFeedbackCreate(BaseModel):
    """Schema for submitting call feedback."""

    source: str = Field(
        default="user",
        description="Feedback source: user, contact, auto_quality, agent_self_eval",
    )
    rating: int | None = Field(None, ge=1, le=5, description="1-5 star rating")
    thumbs: str | None = Field(None, pattern="^(up|down)$", description="Thumbs up or down")
    feedback_text: str | None = Field(None, max_length=2000)
    feedback_signals: dict[str, Any] = Field(default_factory=dict)
    quality_score: float | None = Field(None, ge=0.0, le=1.0)
    quality_reasoning: str | None = None


class CallFeedbackResponse(BaseModel):
    """Schema for call feedback response."""

    id: uuid.UUID
    message_id: uuid.UUID
    call_outcome_id: uuid.UUID | None
    source: str
    user_id: int | None
    rating: int | None
    thumbs: str | None
    feedback_text: str | None
    feedback_signals: dict[str, Any]
    quality_score: float | None
    quality_reasoning: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CallFeedbackListResponse(BaseModel):
    """Schema for list of feedback for a call."""

    items: list[CallFeedbackResponse]
    total: int


class CallFeedbackSummary(BaseModel):
    """Schema for aggregated feedback summary."""

    message_id: uuid.UUID
    total_feedback: int
    avg_rating: float | None
    avg_quality_score: float | None
    thumbs_up_count: int
    thumbs_down_count: int
    has_user_feedback: bool
    has_auto_quality: bool
