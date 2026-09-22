"""Exceptional-fidelity gate for promoting sim-winning strategies to live.

A strategy (a winning first-touch opener / closing strategy) that tops a
simulation ranking is *not* automatically allowed to touch a live iMessage
thread. It must first clear a strict "exceptional" bar enforced here as code.

The bar has two **HARD** gates that must be perfect, and four quality gates:

* HARD ``factual_accuracy`` must be ``1.0`` (100%) — the strategy never makes a
  false claim about Prestyj Batch Video Ads (pricing, pack math, what the batch
  does and does not include).
* HARD ``escalation_precision`` must be ``1.0`` (100%) — the strategy only ever
  escalates to a human for genuine add-ons beyond the batch (running ads,
  AI-agent install, consulting) and never falsely escalates a batch-only buyer
  nor pretends the batch covers an add-on.
* ``anchor_discipline`` >= 0.95 — keeps the 500-pack anchoring discipline.
* ``objection_coverage`` >= 90 / 100 — answers the objections that come up.
* ``on_brand_tone`` >= 85 / 100 — stays on-brand.
* ``close_rate`` >= 0.40 of *engaged* personas, sustained over >= 200
  simulated conversations.

Below the bar, the caller keeps the strategy in sim/shadow; it never gets
registered as a live variant. The thresholds are module-level constants so the
bar is tunable in one place.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

# ── Configurable thresholds (the "exceptional" bar) ──────────────────────────
# Edit these constants to retune the gate. HARD gates are exact-match perfection.

# HARD gates — must be exactly perfect (1.0 == 100%).
HARD_FACTUAL_ACCURACY: float = 1.0
HARD_ESCALATION_PRECISION: float = 1.0

# Quality gates — minimum acceptable values.
MIN_ANCHOR_DISCIPLINE: float = 0.95  # fraction 0-1
MIN_OBJECTION_COVERAGE: float = 90.0  # 0-100 scale
MIN_ON_BRAND_TONE: float = 85.0  # 0-100 scale
MIN_CLOSE_RATE: float = 0.40  # fraction of engaged personas, 0-1

# The close rate must be *sustained* over at least this many simulated
# conversations before it counts as evidence rather than noise.
MIN_SUSTAINED_CONVERSATIONS: int = 200

# Funnel stages that count as "engaged" (the denominator for close rate).
_ENGAGED_STAGES: frozenset[str] = frozenset({"engaged", "agreed_to_buy"})
_CLOSED_STAGES: frozenset[str] = frozenset({"agreed_to_buy"})


@dataclass(frozen=True, slots=True)
class StrategyScorecard:
    """The promotion-eligibility contract a simulation must fill in.

    Behavioural counts (``close_rate``, ``escalation_precision``,
    ``total_conversations``, ``engaged_conversations``) are derived
    deterministically from simulated conversation outcomes; the quality
    judgments (``factual_accuracy``, ``anchor_discipline``,
    ``objection_coverage``, ``on_brand_tone``) come from the rehearsal/funnel
    scorer. Use :func:`build_scorecard_from_outcomes` to assemble one from the
    opener-optimizer outcome rows.
    """

    opener_id: str
    opener_text: str
    strategy: str | None

    # HARD-gate dimensions (0-1 fractions).
    factual_accuracy: float
    escalation_precision: float

    # Quality dimensions.
    anchor_discipline: float  # 0-1 fraction
    objection_coverage: float  # 0-100
    on_brand_tone: float  # 0-100

    # Outcome dimensions.
    close_rate: float  # 0-1, closes / engaged
    total_conversations: int
    engaged_conversations: int


@dataclass(frozen=True, slots=True)
class CriterionResult:
    """The pass/fail of one gate criterion."""

    name: str
    value: float
    threshold: float
    comparator: str  # ">=", "==", e.g.
    passed: bool
    is_hard_gate: bool
    detail: str


@dataclass(slots=True)
class FidelityGateResult:
    """The verdict of evaluating a scorecard against the exceptional bar."""

    passed: bool
    criteria: list[CriterionResult] = field(default_factory=list)

    @property
    def hard_gate_failures(self) -> list[CriterionResult]:
        return [c for c in self.criteria if c.is_hard_gate and not c.passed]

    @property
    def soft_failures(self) -> list[CriterionResult]:
        return [c for c in self.criteria if not c.is_hard_gate and not c.passed]

    @property
    def failures(self) -> list[CriterionResult]:
        return [c for c in self.criteria if not c.passed]

    def summary(self) -> str:
        if self.passed:
            return "cleared exceptional fidelity gate"
        parts = [
            f"{c.name} {c.value:g} {c.comparator} {c.threshold:g} failed" for c in self.failures
        ]
        return "; ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "summary": self.summary(),
            "criteria": [
                {
                    "name": c.name,
                    "value": c.value,
                    "threshold": c.threshold,
                    "comparator": c.comparator,
                    "passed": c.passed,
                    "is_hard_gate": c.is_hard_gate,
                    "detail": c.detail,
                }
                for c in self.criteria
            ],
        }


def evaluate_fidelity_gate(
    scorecard: StrategyScorecard,
    *,
    hard_factual_accuracy: float = HARD_FACTUAL_ACCURACY,
    hard_escalation_precision: float = HARD_ESCALATION_PRECISION,
    min_anchor_discipline: float = MIN_ANCHOR_DISCIPLINE,
    min_objection_coverage: float = MIN_OBJECTION_COVERAGE,
    min_on_brand_tone: float = MIN_ON_BRAND_TONE,
    min_close_rate: float = MIN_CLOSE_RATE,
    min_sustained_conversations: int = MIN_SUSTAINED_CONVERSATIONS,
) -> FidelityGateResult:
    """Evaluate a scorecard against the exceptional bar.

    Every criterion is checked (no short-circuit) so the result carries a full
    per-criterion breakdown for observability. The overall verdict passes only
    when *all* criteria pass; any HARD-gate miss or quality miss fails it.
    """
    criteria: list[CriterionResult] = []

    # HARD gate: factual accuracy must be perfect.
    criteria.append(
        CriterionResult(
            name="factual_accuracy",
            value=scorecard.factual_accuracy,
            threshold=hard_factual_accuracy,
            comparator="==",
            passed=scorecard.factual_accuracy >= hard_factual_accuracy,
            is_hard_gate=True,
            detail="HARD: every factual claim about the batch must be correct",
        )
    )

    # HARD gate: escalation precision must be perfect.
    criteria.append(
        CriterionResult(
            name="escalation_precision",
            value=scorecard.escalation_precision,
            threshold=hard_escalation_precision,
            comparator="==",
            passed=scorecard.escalation_precision >= hard_escalation_precision,
            is_hard_gate=True,
            detail="HARD: only ever escalate genuine add-ons beyond the batch",
        )
    )

    # Quality gate: anchor discipline.
    criteria.append(
        CriterionResult(
            name="anchor_discipline",
            value=scorecard.anchor_discipline,
            threshold=min_anchor_discipline,
            comparator=">=",
            passed=scorecard.anchor_discipline >= min_anchor_discipline,
            is_hard_gate=False,
            detail="hold the 500-pack anchoring discipline",
        )
    )

    # Quality gate: objection coverage.
    criteria.append(
        CriterionResult(
            name="objection_coverage",
            value=scorecard.objection_coverage,
            threshold=min_objection_coverage,
            comparator=">=",
            passed=scorecard.objection_coverage >= min_objection_coverage,
            is_hard_gate=False,
            detail="address the objections prospects actually raise",
        )
    )

    # Quality gate: on-brand tone.
    criteria.append(
        CriterionResult(
            name="on_brand_tone",
            value=scorecard.on_brand_tone,
            threshold=min_on_brand_tone,
            comparator=">=",
            passed=scorecard.on_brand_tone >= min_on_brand_tone,
            is_hard_gate=False,
            detail="stay on-brand in tone",
        )
    )

    # Quality gate: sustained sample size.
    criteria.append(
        CriterionResult(
            name="total_conversations",
            value=float(scorecard.total_conversations),
            threshold=float(min_sustained_conversations),
            comparator=">=",
            passed=scorecard.total_conversations >= min_sustained_conversations,
            is_hard_gate=False,
            detail="close rate must be sustained over enough conversations",
        )
    )

    # Quality gate: close rate among engaged personas.
    criteria.append(
        CriterionResult(
            name="close_rate",
            value=scorecard.close_rate,
            threshold=min_close_rate,
            comparator=">=",
            passed=scorecard.close_rate >= min_close_rate,
            is_hard_gate=False,
            detail="close >= 40% of engaged personas",
        )
    )

    passed = all(c.passed for c in criteria)
    return FidelityGateResult(passed=passed, criteria=criteria)


def _stage_of(row: Any) -> str:
    """Read the funnel stage off an outcome row (dataclass or mapping)."""
    if isinstance(row, Mapping):
        return str(row.get("stage") or "")
    return str(getattr(row, "stage", "") or "")


def _field(row: Any, name: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(name, default)
    return getattr(row, name, default)


def build_scorecard_from_outcomes(
    *,
    opener_id: str,
    opener_text: str,
    strategy: str | None,
    outcomes: Iterable[Any],
    escalation_personas: Iterable[str],
    factual_accuracy: float,
    anchor_discipline: float,
    objection_coverage: float,
    on_brand_tone: float,
) -> StrategyScorecard:
    """Assemble a :class:`StrategyScorecard` from simulated outcome rows.

    Deterministic behavioural metrics are computed from the outcome rows
    (each is an ``opener_optimizer.ConversationOutcome`` or an equivalent
    mapping carrying ``stage``, ``reached_close``, ``escalated``,
    ``persona_slug``):

    * ``close_rate`` = closed conversations / engaged conversations.
    * ``escalation_precision`` = correct escalations / total escalations
      (vacuously ``1.0`` when the strategy never escalates — it can't have a
      false escalation if it never escalated).
    * ``total_conversations`` / ``engaged_conversations`` counts.

    The quality judgments (``factual_accuracy``, ``anchor_discipline``,
    ``objection_coverage``, ``on_brand_tone``) are supplied by the scorer and
    passed through.
    """
    warranted = set(escalation_personas)
    rows = list(outcomes)

    total = len(rows)
    engaged = 0
    closed = 0
    escalations = 0
    correct_escalations = 0

    for row in rows:
        stage = _stage_of(row)
        reached_close = bool(_field(row, "reached_close", False))
        if stage in _ENGAGED_STAGES:
            engaged += 1
        if stage in _CLOSED_STAGES or reached_close:
            closed += 1
        if bool(_field(row, "escalated", False)):
            escalations += 1
            if str(_field(row, "persona_slug", "")) in warranted:
                correct_escalations += 1

    close_rate = (closed / engaged) if engaged > 0 else 0.0
    escalation_precision = (correct_escalations / escalations) if escalations > 0 else 1.0

    return StrategyScorecard(
        opener_id=opener_id,
        opener_text=opener_text,
        strategy=strategy,
        factual_accuracy=factual_accuracy,
        escalation_precision=escalation_precision,
        anchor_discipline=anchor_discipline,
        objection_coverage=objection_coverage,
        on_brand_tone=on_brand_tone,
        close_rate=round(close_rate, 4),
        total_conversations=total,
        engaged_conversations=engaged,
    )
