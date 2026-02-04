"""Reward recording service for multi-armed bandit learning."""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bandit_decision import BanditDecision
from app.models.call_outcome import CallOutcome
from app.models.prompt_version import PromptVersion
from app.services.ai.reward_config import RewardConfig, compute_reward

logger = structlog.get_logger()


class BanditRewardService:
    """Records rewards and updates bandit statistics."""

    def __init__(self, reward_config: RewardConfig | None = None):
        """Initialize with optional custom reward config."""
        self.reward_config = reward_config

    async def record_reward(
        self,
        db: AsyncSession,
        outcome: CallOutcome,
    ) -> float | None:
        """Record reward for a call outcome and update bandit statistics.

        Finds the BanditDecision associated with the outcome's message_id,
        computes the reward, and updates both the decision and the prompt
        version's bandit statistics.

        Args:
            db: Database session
            outcome: CallOutcome to compute reward for

        Returns:
            Computed reward value if a BanditDecision was found, None otherwise
        """
        log = logger.bind(
            service="bandit_reward",
            outcome_id=str(outcome.id),
            message_id=str(outcome.message_id),
            outcome_type=outcome.outcome_type,
        )

        # Find the BanditDecision for this message
        decision_result = await db.execute(
            select(BanditDecision).where(BanditDecision.message_id == outcome.message_id)
        )
        decision = decision_result.scalar_one_or_none()

        if decision is None:
            # No bandit decision for this call (might be before bandit integration)
            log.debug("no_bandit_decision_found")
            return None

        if decision.observed_reward is not None:
            # Reward already recorded
            log.debug(
                "reward_already_recorded",
                existing_reward=decision.observed_reward,
            )
            return decision.observed_reward

        # Compute reward
        reward = compute_reward(
            outcome_type=outcome.outcome_type,
            signals=outcome.signals,
            config=self.reward_config,
        )

        # Update the decision
        decision.observed_reward = reward
        decision.reward_observed_at = datetime.now(UTC)

        # Update the prompt version's bandit statistics
        version_result = await db.execute(
            select(PromptVersion).where(PromptVersion.id == decision.arm_id)
        )
        version = version_result.scalar_one_or_none()

        if version:
            # Update Beta distribution parameters
            # For binary rewards: alpha += success, beta += failure
            # For continuous rewards [0,1]: alpha += reward, beta += (1 - reward)
            version.bandit_alpha += reward
            version.bandit_beta += 1.0 - reward
            version.total_reward += reward
            version.reward_count += 1

            log.info(
                "bandit_stats_updated",
                version_id=str(version.id),
                reward=reward,
                new_alpha=version.bandit_alpha,
                new_beta=version.bandit_beta,
                reward_count=version.reward_count,
            )

        await db.commit()

        log.info(
            "reward_recorded",
            decision_id=str(decision.id),
            reward=reward,
        )

        return reward

    async def record_reward_by_message(
        self,
        db: AsyncSession,
        message_id: uuid.UUID,
        outcome_type: str,
        signals: dict[str, object] | None = None,
    ) -> float | None:
        """Record reward directly by message ID without requiring CallOutcome.

        Useful for recording rewards when the outcome is known but CallOutcome
        hasn't been created yet.

        Args:
            db: Database session
            message_id: Message ID to record reward for
            outcome_type: The call outcome type
            signals: Optional outcome signals

        Returns:
            Computed reward value if a BanditDecision was found, None otherwise
        """
        log = logger.bind(
            service="bandit_reward",
            message_id=str(message_id),
            outcome_type=outcome_type,
        )

        # Find the BanditDecision for this message
        decision_result = await db.execute(
            select(BanditDecision).where(BanditDecision.message_id == message_id)
        )
        decision = decision_result.scalar_one_or_none()

        if decision is None:
            log.debug("no_bandit_decision_found")
            return None

        if decision.observed_reward is not None:
            log.debug(
                "reward_already_recorded",
                existing_reward=decision.observed_reward,
            )
            return decision.observed_reward

        # Compute reward
        reward = compute_reward(
            outcome_type=outcome_type,
            signals=signals,
            config=self.reward_config,
        )

        # Update the decision
        decision.observed_reward = reward
        decision.reward_observed_at = datetime.now(UTC)

        # Update the prompt version's bandit statistics
        version_result = await db.execute(
            select(PromptVersion).where(PromptVersion.id == decision.arm_id)
        )
        version = version_result.scalar_one_or_none()

        if version:
            version.bandit_alpha += reward
            version.bandit_beta += 1.0 - reward
            version.total_reward += reward
            version.reward_count += 1

            log.info(
                "bandit_stats_updated",
                version_id=str(version.id),
                reward=reward,
                new_alpha=version.bandit_alpha,
                new_beta=version.bandit_beta,
            )

        await db.commit()

        log.info(
            "reward_recorded",
            decision_id=str(decision.id),
            reward=reward,
        )

        return reward


# Module-level singleton for convenience
_default_service: BanditRewardService | None = None


def get_bandit_reward_service() -> BanditRewardService:
    """Get the default BanditRewardService instance."""
    global _default_service
    if _default_service is None:
        _default_service = BanditRewardService()
    return _default_service


async def record_bandit_reward(
    db: AsyncSession,
    outcome: CallOutcome,
) -> float | None:
    """Convenience function to record reward using the default service."""
    service = get_bandit_reward_service()
    return await service.record_reward(db, outcome)
