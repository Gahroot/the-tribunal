"""Prompt improvement worker for automated suggestion generation.

Periodically analyzes agent performance and generates improvement
suggestions for agents with auto_suggest or auto_activate enabled.
"""

import math

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.agent import Agent
from app.models.appointment import Appointment, AppointmentStatus
from app.models.call_outcome import CallOutcome
from app.models.conversation import Message
from app.models.improvement_suggestion import ImprovementSuggestion
from app.models.prompt_version import PromptVersion
from app.services.ai.model_config import resolve_model
from app.services.ai.prompt_improvement_service import PromptImprovementService
from app.services.ai.prompt_scenario_suite import require_scenario_pass
from app.workers.base import BaseWorker, WorkerRegistry
from app.workers.retryable import RetryableWorker


def _eligible_score(judge: object) -> float | None:
    if not isinstance(judge, dict):
        return None
    score, confidence = judge.get("score"), judge.get("confidence")
    if (
        judge.get("human_review") is not False
        or judge.get("rubric_version") != 1
        or not isinstance(judge.get("scores"), dict)
        or len(judge["scores"]) != 5
        or not isinstance(score, (int, float))
        or isinstance(score, bool)
        or not math.isfinite(score)
        or not 0 <= score <= 1
        or not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not math.isfinite(confidence)
        or confidence < 0.7
    ):
        return None
    return float(score)


class PromptImprovementWorker(RetryableWorker, BaseWorker):
    """Generates prompt improvement suggestions automatically.

    Runs daily to analyze agents with auto_suggest=True and generate
    improvement suggestions. With auto_activate, promotes approved candidates
    only after a human-started canary has judged calls and verified outcomes.
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
            score = _eligible_score((signals or {}).get("judge"))
            if score is None:
                return False
            scores.append(score)
            positive_outcomes += booking_outcome == "success" or shown is True
        return (
            sum(scores) / len(scores) >= 0.8
            and positive_outcomes >= 1
            and positive_outcomes / len(rows) >= 0.1
        )

    async def _promote_tested_candidate(self, db: AsyncSession, agent: Agent) -> bool:
        """Promote only an approved candidate already exposed in a human-started test."""
        result = await db.execute(
            select(PromptVersion)
            .join(
                ImprovementSuggestion, ImprovementSuggestion.created_version_id == PromptVersion.id
            )
            .where(
                ImprovementSuggestion.agent_id == agent.id,
                ImprovementSuggestion.status == "approved",
                PromptVersion.is_active.is_(True),
                PromptVersion.arm_status == "active",
            )
            .order_by(PromptVersion.version_number.desc())
        )
        for candidate in result.scalars():
            if not await self._can_auto_activate(db, candidate):
                continue
            # Outcome evidence alone cannot promote a prompt: test the candidate
            # itself before deactivating the current version.
            await require_scenario_pass(
                candidate,
                simulation=await resolve_model(
                    db, "prompt_improvement", agent.workspace_id, agent.id
                ),
                judgment=await resolve_model(
                    db, "transcript_judgment", agent.workspace_id, agent.id
                ),
            )
            updated = await db.execute(
                update(PromptVersion)
                .where(
                    PromptVersion.agent_id == agent.id,
                    PromptVersion.id != candidate.id,
                    PromptVersion.is_active.is_(True),
                )
                .values(is_active=False)
                .returning(PromptVersion.id)
            )
            if updated.first() is not None:
                await db.commit()
                return True
        return False

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

        # Manual canary exposure comes first; only its own judged calls can
        # promote a candidate to exclusive live use.
        if agent.auto_activate and await self._promote_tested_candidate(db, agent):
            return

        # Get active version
        version_result = await db.execute(
            select(PromptVersion)
            .where(
                PromptVersion.agent_id == agent.id,
                PromptVersion.is_active.is_(True),
                PromptVersion.arm_status == "active",
            )
            .order_by(PromptVersion.version_number.asc())
        )
        active_version = version_result.scalars().first()

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

        if pending_suggestions:
            log.debug(
                "Pending suggestions exist, skipping generation",
                pending_count=len(pending_suggestions),
            )
            return

        # A new prompt has no outcome evidence yet. Leave its suggestion
        # pending until a human starts a canary through the existing approval flow.
        service = PromptImprovementService()

        # Generate new suggestions
        log.info("Generating improvement suggestions")

        try:
            # Analyze performance
            analysis = await service.analyze_performance(db, active_version)

            # Generate variations (just 1 for auto-mode)
            variations = await service.generate_variations(
                active_version,
                analysis,
                num_variations=1,
                selection=await service._selection(db, active_version),
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

        except Exception as e:
            log.error("Failed to generate suggestions", error=str(e))


# Singleton registry
_registry = WorkerRegistry(PromptImprovementWorker)
start_prompt_improvement_worker = _registry.start
stop_prompt_improvement_worker = _registry.stop
get_prompt_improvement_worker = _registry.get
