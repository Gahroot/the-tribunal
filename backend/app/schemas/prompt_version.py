"""Pydantic schemas for PromptVersion."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PromptVersionCreate(BaseModel):
    """Schema for creating a new prompt version."""

    system_prompt: str | None = None  # If None, snapshot from current agent
    initial_greeting: str | None = None
    temperature: float | None = None
    change_summary: str | None = Field(None, max_length=500)
    is_baseline: bool = False
    traffic_percentage: int | None = Field(None, ge=0, le=100)
    experiment_id: uuid.UUID | None = None


class PromptVersionUpdate(BaseModel):
    """Schema for updating a prompt version (limited fields)."""

    change_summary: str | None = Field(None, max_length=500)
    is_baseline: bool | None = None
    traffic_percentage: int | None = Field(None, ge=0, le=100)
    experiment_id: uuid.UUID | None = None


class PromptVersionResponse(BaseModel):
    """Schema for prompt version response."""

    id: uuid.UUID
    agent_id: uuid.UUID
    system_prompt: str
    initial_greeting: str | None
    temperature: float
    version_number: int
    change_summary: str | None
    created_by_id: int | None
    is_active: bool
    is_baseline: bool
    parent_version_id: uuid.UUID | None
    total_calls: int
    successful_calls: int
    booked_appointments: int
    # Multi-variant A/B testing fields
    traffic_percentage: int | None
    experiment_id: uuid.UUID | None
    arm_status: str
    # Bandit statistics
    bandit_alpha: float
    bandit_beta: float
    total_reward: float
    reward_count: int
    created_at: datetime
    activated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class PromptVersionListResponse(BaseModel):
    """Schema for paginated prompt version list."""

    items: list[PromptVersionResponse]
    total: int
    page: int
    page_size: int
    pages: int


class PromptVersionStatsResponse(BaseModel):
    """Schema for prompt version performance stats."""

    prompt_version_id: uuid.UUID
    version_number: int
    is_active: bool
    is_baseline: bool

    # Aggregate stats
    total_calls: int
    completed_calls: int
    failed_calls: int
    appointments_booked: int
    leads_qualified: int

    # Rates
    booking_rate: float | None
    qualification_rate: float | None
    completion_rate: float | None

    # Quality
    avg_duration_seconds: float | None
    avg_quality_score: float | None

    # Time range
    stats_from: datetime | None = None
    stats_to: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class PromptVersionActivateResponse(BaseModel):
    """Schema for prompt version activation response."""

    activated_version: PromptVersionResponse
    deactivated_version_id: uuid.UUID | None = None


class PromptVersionRollbackResponse(BaseModel):
    """Schema for prompt version rollback response."""

    new_version: PromptVersionResponse
    rolled_back_from: uuid.UUID


class VersionComparisonItem(BaseModel):
    """Schema for individual version comparison stats."""

    version_id: uuid.UUID
    version_number: int
    is_active: bool
    is_baseline: bool
    arm_status: str
    probability_best: float
    credible_interval_lower: float
    credible_interval_upper: float
    sample_size: int
    booking_rate: float | None
    mean_estimate: float


class VersionComparisonResponse(BaseModel):
    """Schema for comparing all active versions."""

    versions: list[VersionComparisonItem]
    winner_id: uuid.UUID | None
    winner_probability: float | None
    recommended_action: str  # "continue", "declare_winner", "eliminate_worst"
    min_samples_needed: int


class WinnerDetectionResponse(BaseModel):
    """Schema for winner detection result."""

    winner_id: uuid.UUID | None
    winner_probability: float | None
    confidence_threshold: float
    is_conclusive: bool
    message: str


class ArmStatusUpdate(BaseModel):
    """Schema for updating arm status."""

    arm_status: str = Field(..., pattern="^(active|paused|eliminated)$")
