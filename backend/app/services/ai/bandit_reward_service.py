"""Reward recording service for multi-armed bandit learning."""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.bandit_decision import BanditDecision
from app.models.call_outcome import CallOutcome
from app.models.conversation import Message
from app.models.prompt_version import PromptVersion
from app.services.ai.reward_config import RewardConfig, compute_call_reward

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
            select(BanditDecision)
            .where(BanditDecision.message_id == outcome.message_id)
            .with_for_update()
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

        # Wait for the terminal, evidence-backed evaluation on voice calls.
        if (outcome.signals or {}).get("live_only"):
            return None
        message = await db.get(Message, outcome.message_id)
        if message is None:
            return None
        judge = (outcome.signals or {}).get("judge")
        # Never finalize a voice reward without verified rubric evidence. A late
        # transcript or a recovered judge may still provide it on a later poll.
        if message.channel == "voice" and not (
            isinstance(judge, dict)
            and isinstance(judge.get("scores"), dict)
            and isinstance(judge.get("score"), (int, float))
            and len(judge["scores"]) == 5
        ):
            return None
        agent = await db.get(Agent, decision.agent_id)
        reward = compute_call_reward(
            outcome_type=outcome.outcome_type,
            signals=outcome.signals,
            judge=judge if isinstance(judge, dict) else None,
            duration_seconds=message.duration_seconds,
            overrides=agent.bandit_reward_config if agent else None,
            config=self.reward_config,
        )

        # Update the decision
        decision.observed_reward = reward
        decision.reward_observed_at = datetime.now(UTC)

        # Update the prompt version's bandit statistics
        version_result = await db.execute(
            select(PromptVersion).where(PromptVersion.id == decision.arm_id).with_for_update()
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
        """Use the persisted outcome; never reward an unverified transient result."""
        outcome = await db.scalar(select(CallOutcome).where(CallOutcome.message_id == message_id))
        if outcome is None:
            return None
        return await self.record_reward(db, outcome)


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
