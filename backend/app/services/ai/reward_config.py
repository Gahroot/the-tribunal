"""Reward configuration and computation for multi-armed bandit optimization."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RewardConfig:
    """Configurable reward weights for different call outcomes.

    Weights are normalized to produce rewards in [0.0, 1.0] range.
    appointment_booked is the primary optimization target.
    """

    appointment_booked: float = 1.0  # Primary goal
    lead_qualified: float = 0.6
    completed: float = 0.3
    voicemail: float = 0.1
    no_answer: float = 0.0
    busy: float = 0.0
    rejected: float = 0.0
    failed: float = 0.0

    # Signal-based bonuses (added to base reward)
    signal_weights: dict[str, float] = field(
        default_factory=lambda: {
            "booking_attempted": 0.1,  # Bonus for attempting to book
            "call_completed": 0.05,  # Bonus for completing the call
        }
    )

    def get_outcome_weight(self, outcome_type: str) -> float:
        """Get the base reward weight for an outcome type."""
        weight_map = {
            "appointment_booked": self.appointment_booked,
            "lead_qualified": self.lead_qualified,
            "completed": self.completed,
            "voicemail": self.voicemail,
            "no_answer": self.no_answer,
            "busy": self.busy,
            "rejected": self.rejected,
            "failed": self.failed,
        }
        return weight_map.get(outcome_type, 0.0)


# Default reward configuration
DEFAULT_REWARD_CONFIG = RewardConfig()


def compute_reward(
    outcome_type: str,
    signals: dict[str, Any] | None = None,
    config: RewardConfig | None = None,
) -> float:
    """Compute the reward value for a call outcome.

    Args:
        outcome_type: The call outcome type (e.g., "appointment_booked", "completed")
        signals: Optional signal dict with additional outcome indicators
        config: Optional reward config (uses default if not provided)

    Returns:
        Reward value in [0.0, 1.0] range
    """
    if config is None:
        config = DEFAULT_REWARD_CONFIG

    # Start with base reward for outcome type
    reward = config.get_outcome_weight(outcome_type)

    # Add signal-based bonuses (capped at 1.0)
    if signals:
        for signal_name, weight in config.signal_weights.items():
            if signals.get(signal_name):
                reward += weight

    # Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, reward))
