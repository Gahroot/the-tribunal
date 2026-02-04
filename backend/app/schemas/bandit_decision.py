"""Pydantic schemas for BanditDecision."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BanditDecisionResponse(BaseModel):
    """Schema for bandit decision response."""

    id: uuid.UUID
    agent_id: uuid.UUID
    arm_id: uuid.UUID
    message_id: uuid.UUID | None
    decision_type: str
    exploration_rate: float | None
    arm_statistics: dict[str, Any]
    context_snapshot: dict[str, Any]
    observed_reward: float | None
    reward_observed_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BanditArmStats(BaseModel):
    """Statistics for a single bandit arm (prompt version)."""

    arm_id: uuid.UUID
    version_number: int
    alpha: float = Field(..., description="Beta distribution alpha parameter")
    beta: float = Field(..., description="Beta distribution beta parameter")
    mean_reward: float = Field(..., description="Mean observed reward")
    reward_count: int = Field(..., description="Number of reward observations")
    is_active: bool
    is_baseline: bool


class BanditAgentStats(BaseModel):
    """Aggregated bandit statistics for an agent."""

    agent_id: uuid.UUID
    total_decisions: int
    total_rewards_observed: int
    arms: list[BanditArmStats]


class BanditDecisionCreate(BaseModel):
    """Schema for manually creating a bandit decision (for testing)."""

    agent_id: uuid.UUID
    arm_id: uuid.UUID
    message_id: uuid.UUID | None = None
    decision_type: str = "thompson_sampling"
    exploration_rate: float | None = None
    arm_statistics: dict[str, Any] = Field(default_factory=dict)
    context_snapshot: dict[str, Any] = Field(default_factory=dict)


class BanditRewardUpdate(BaseModel):
    """Schema for recording a reward on a bandit decision."""

    observed_reward: float = Field(..., ge=0.0, le=1.0)
