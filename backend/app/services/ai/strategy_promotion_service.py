"""Promote sim-winning strategies into live prompt-version variants.

This is the bridge from simulation to production. A strategy that wins a
simulation ranking is handed here with its :class:`StrategyScorecard`. The
service enforces the exceptional-fidelity gate
(:func:`app.services.ai.fidelity_gate.evaluate_fidelity_gate`) and only when the
gate passes does it register the strategy as a live prompt-version variant
(``initial_greeting`` = the winning opener) and activate it for multi-variant
testing.

Once activated for testing, the variant is ``is_active`` + ``arm_status=active``,
so it is picked up automatically by:

* the bandit arm selector / live text agent (it can now serve real threads), and
* :class:`app.workers.experiment_evaluation_worker.ExperimentEvaluationWorker`,
  which compares the active variants and auto-graduates winners.

When the gate fails, **nothing live is created**: the strategy stays in
sim/shadow and never touches a live thread.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt_version import PromptVersion
from app.services.ai.fidelity_gate import (
    FidelityGateResult,
    StrategyScorecard,
    evaluate_fidelity_gate,
)
from app.services.ai.prompt_version_service import PromptVersionService

logger = structlog.get_logger()

Disposition = Literal["promoted_to_live", "held_in_shadow"]


@dataclass(slots=True)
class PromotionResult:
    """Outcome of attempting to promote a strategy to a live variant."""

    promoted: bool
    disposition: Disposition
    gate_result: FidelityGateResult
    prompt_version: PromptVersion | None
    reason: str


class StrategyPromotionService:
    """Gate-enforced promotion of simulation winners to live variants."""

    def __init__(self, prompt_versions: PromptVersionService | None = None) -> None:
        self._prompt_versions = prompt_versions or PromptVersionService()

    async def promote_if_exceptional(
        self,
        db: AsyncSession,
        *,
        agent_id: uuid.UUID,
        scorecard: StrategyScorecard,
        created_by_id: int | None = None,
        experiment_id: uuid.UUID | None = None,
    ) -> PromotionResult:
        """Promote a strategy to a live variant only if it clears the gate.

        On pass: creates a new prompt version whose ``initial_greeting`` is the
        winning opener, then activates it for multi-variant testing so it feeds
        the live message-test + experiment-evaluation loop. On fail: creates
        nothing and reports the strategy as held in shadow.
        """
        log = logger.bind(
            service="strategy_promotion",
            agent_id=str(agent_id),
            opener_id=scorecard.opener_id,
            strategy=scorecard.strategy,
        )

        gate_result = evaluate_fidelity_gate(scorecard)

        if not gate_result.passed:
            log.info(
                "strategy_held_in_shadow",
                summary=gate_result.summary(),
                hard_gate_failures=[c.name for c in gate_result.hard_gate_failures],
                soft_failures=[c.name for c in gate_result.soft_failures],
            )
            return PromotionResult(
                promoted=False,
                disposition="held_in_shadow",
                gate_result=gate_result,
                prompt_version=None,
                reason=f"below exceptional bar: {gate_result.summary()}",
            )

        log.info("strategy_cleared_gate", close_rate=scorecard.close_rate)

        change_summary = (
            f"Promoted sim-winning strategy '{scorecard.strategy or scorecard.opener_id}': "
            f"close_rate={scorecard.close_rate:.0%} over {scorecard.total_conversations} sims, "
            f"factual={scorecard.factual_accuracy:.0%}, "
            f"escalation_precision={scorecard.escalation_precision:.0%}, "
            f"anchor={scorecard.anchor_discipline:.0%}, "
            f"objection={scorecard.objection_coverage:g}, tone={scorecard.on_brand_tone:g}"
        )

        version = await self._prompt_versions.create_version(
            db=db,
            agent_id=agent_id,
            initial_greeting=scorecard.opener_text,
            change_summary=change_summary,
            created_by_id=created_by_id,
            is_baseline=False,
            activate=False,
            experiment_id=experiment_id,
        )

        # Activate as a live A/B arm without deactivating existing variants, so
        # it joins the multi-variant set the experiment-evaluation loop compares.
        activated = await self._prompt_versions.activate_for_testing(db, version.id)

        log.info(
            "strategy_promoted_to_live",
            version_id=str(activated.id),
            version_number=activated.version_number,
        )

        return PromotionResult(
            promoted=True,
            disposition="promoted_to_live",
            gate_result=gate_result,
            prompt_version=activated,
            reason="cleared exceptional fidelity gate",
        )
