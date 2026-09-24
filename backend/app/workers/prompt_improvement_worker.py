"""Prompt improvement worker for automated suggestion generation.

Periodically analyzes agent performance and generates improvement
suggestions for agents with auto_suggest or auto_activate enabled.
"""

import math

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.agent import Agent
from app.models.appointment import Appointment, AppointmentStatus
from app.models.call_outcome import CallOutcome
from app.models.conversation import Message
from app.models.improvement_suggestion import ImprovementSuggestion
from app.models.prompt_version import PromptVersion
from app.services.ai.prompt_improvement_service import PromptImprovementService
from app.workers.base import BaseWorker, WorkerRegistry
from app.workers.retryable import RetryableWorker


class PromptImprovementWorker(RetryableWorker, BaseWorker):
    """Generates prompt improvement suggestions automatically.

    Runs daily to analyze agents with auto_suggest=True and generate
    improvement suggestions. If auto_activate=True, also auto-approves
    suggestions when no pending suggestions exist.
    """

    POLL_INTERVAL_SECONDS = 86400  # Daily
    COMPONENT_NAME = "prompt_improvement"
    # Per-agent suggestion generation hits OpenAI — keep concurrency low
    # so a single cycle can't burst through the org rate limit.
    MAX_CONCURRENCY = 3
    max_retries = 3
    backoff_base_seconds = 2.0

    async def _process_items(self) -> None:
        """Process agents with auto-improvement enabled."""
        async with AsyncSessionLocal() as db:
            # Find agents with auto_suggest or auto_activate enabled
            result = await db.execute(
                select(Agent).where(
                    Agent.is_active.is_(True),
                    (Agent.auto_suggest.is_(True) | Agent.auto_activate.is_(True)),
                )
            )
            agents = list(result.scalars().all())

            if not agents:
                self.logger.debug("No agents with auto-improvement enabled")
                return

            self.logger.info("Processing auto-improvement agents", count=len(agents))

            for agent in agents:
                await self.execute_with_retry(
                    self._process_agent,
                    db,
                    agent,
                    item_key=f"agent:{agent.id}",
                )

            await db.commit()

    async def _can_auto_activate(self, db: AsyncSession, version: PromptVersion) -> bool:
        """Require real booking evidence AND reliable quality across recent calls."""
        result = await db.execute(
            select(
                CallOutcome.signals,
                Message.booking_outcome,
                exists().where(
                    Appointment.message_id == Message.id,
                    Appointment.status == AppointmentStatus.COMPLETED,
                ),
            )
            .join(Message, Message.id == CallOutcome.message_id)
            .where(
                CallOutcome.prompt_version_id == version.id,
                Message.channel == "voice",
                Message.transcript.is_not(None),
            )
            .order_by(CallOutcome.created_at.desc())
            .limit(100)
        )
        rows = result.all()
        if len(rows) < 10:
            return False
        scores = []
        positive_outcomes = 0
        for signals, booking_outcome, shown in rows:
            judge = (signals or {}).get("judge")
            if not isinstance(judge, dict) or judge.get("human_review") is not False:
                return False
            score = judge.get("score")
            if not isinstance(score, (int, float)) or isinstance(score, bool):
                return False
            if not math.isfinite(score) or not 0 <= score <= 1:
                return False
            scores.append(score)
            positive_outcomes += booking_outcome == "success" or shown is True
        return (
            sum(scores) / len(scores) >= 0.8
            and positive_outcomes >= 1
            and positive_outcomes / len(rows) >= 0.1
        )

    async def _process_agent(
        self,
        db: AsyncSession,
        agent: Agent,
    ) -> None:
        """Process a single agent for improvement suggestions.

        Args:
            db: Database session
            agent: Agent to process
        """
        log = self.logger.bind(agent_id=str(agent.id), agent_name=agent.name)

        # Get active version
        version_result = await db.execute(
            select(PromptVersion).where(
                PromptVersion.agent_id == agent.id,
                PromptVersion.is_active.is_(True),
                PromptVersion.arm_status == "active",
            )
        )
        active_version = version_result.scalar_one_or_none()

        if not active_version:
            log.debug("No active version, skipping")
            return

        # Check minimum calls threshold
        if active_version.total_calls < agent.auto_improve_min_calls:
            log.debug(
                "Below minimum calls threshold",
                total_calls=active_version.total_calls,
                min_calls=agent.auto_improve_min_calls,
            )
            return

        # Check for existing pending suggestions
        pending_result = await db.execute(
            select(ImprovementSuggestion).where(
                ImprovementSuggestion.agent_id == agent.id,
                ImprovementSuggestion.status == "pending",
            )
        )
        pending_suggestions = list(pending_result.scalars().all())

        if pending_suggestions and not agent.auto_activate:
            log.debug(
                "Pending suggestions exist, skipping generation",
                pending_count=len(pending_suggestions),
            )
            return

        # No transcript-only auto-promotion: require judged calls AND real bookings.
        can_activate = agent.auto_activate and await self._can_auto_activate(db, active_version)
        service = PromptImprovementService()

        # If auto_activate and there are pending suggestions, approve the first one
        if agent.auto_activate and pending_suggestions:
            top_suggestion = pending_suggestions[0]
            if not can_activate or top_suggestion.source_version_id != active_version.id:
                log.info("Auto-activation gated on judged quality and verified bookings")
                return
            log.info("Auto-activating pending suggestion", suggestion_id=str(top_suggestion.id))

            try:
                await service.approve_suggestion(
                    db=db,
                    suggestion_id=top_suggestion.id,
                    user_id=None,  # System-approved
                    activate=True,
                )
                log.info("Auto-activated suggestion successfully")
            except Exception as e:
                log.error("Failed to auto-activate suggestion", error=str(e))

            return

        # Generate new suggestions
        log.info("Generating improvement suggestions")

        try:
            # Analyze performance
            analysis = await service.analyze_performance(db, active_version)

            # Generate variations (just 1 for auto-mode)
            variations = await service.generate_variations(
                active_version, analysis, num_variations=1
            )

            # Create suggestions
            for variation in variations:
                suggestion = await service.create_suggestion(
                    db=db,
                    version=active_version,
                    variation=variation,
                    analysis_summary=analysis.summary,
                )
                log.info(
                    "Created improvement suggestion",
                    suggestion_id=str(suggestion.id),
                    mutation_type=variation.mutation_type,
                )

                # If auto_activate, approve immediately
                if can_activate:
                    await service.approve_suggestion(
                        db=db,
                        suggestion_id=suggestion.id,
                        user_id=None,
                        activate=True,
                    )
                    log.info("Auto-activated new suggestion")

        except Exception as e:
            log.error("Failed to generate suggestions", error=str(e))


# Singleton registry
_registry = WorkerRegistry(PromptImprovementWorker)
start_prompt_improvement_worker = _registry.start
stop_prompt_improvement_worker = _registry.stop
get_prompt_improvement_worker = _registry.get
