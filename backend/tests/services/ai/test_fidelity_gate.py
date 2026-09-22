"""Tests for the exceptional-fidelity gate and sim->live promotion routing."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ai.fidelity_gate import (
    HARD_FACTUAL_ACCURACY,
    MIN_CLOSE_RATE,
    MIN_SUSTAINED_CONVERSATIONS,
    StrategyScorecard,
    build_scorecard_from_outcomes,
    evaluate_fidelity_gate,
)
from app.services.ai.strategy_promotion_service import StrategyPromotionService


def _exceptional_scorecard(**overrides: object) -> StrategyScorecard:
    """A scorecard that clears every gate, with selective overrides."""
    values: dict[str, object] = {
        "opener_id": "volume_testing",
        "opener_text": "What if you could test 100+ ad variations from one recording?",
        "strategy": "volume_testing",
        "factual_accuracy": 1.0,
        "escalation_precision": 1.0,
        "anchor_discipline": 0.97,
        "objection_coverage": 92.0,
        "on_brand_tone": 88.0,
        "close_rate": 0.45,
        "total_conversations": 224,
        "engaged_conversations": 180,
    }
    values.update(overrides)
    return StrategyScorecard(**values)  # type: ignore[arg-type]


# ── Gate logic ───────────────────────────────────────────────────────────────


def test_exceptional_strategy_passes_gate() -> None:
    result = evaluate_fidelity_gate(_exceptional_scorecard())
    assert result.passed is True
    assert result.failures == []
    assert {c.name for c in result.criteria} == {
        "factual_accuracy",
        "escalation_precision",
        "anchor_discipline",
        "objection_coverage",
        "on_brand_tone",
        "total_conversations",
        "close_rate",
    }


def test_imperfect_factual_accuracy_is_hard_fail() -> None:
    result = evaluate_fidelity_gate(_exceptional_scorecard(factual_accuracy=0.99))
    assert result.passed is False
    assert [c.name for c in result.hard_gate_failures] == ["factual_accuracy"]


def test_imperfect_escalation_precision_is_hard_fail() -> None:
    result = evaluate_fidelity_gate(_exceptional_scorecard(escalation_precision=0.95))
    assert result.passed is False
    assert [c.name for c in result.hard_gate_failures] == ["escalation_precision"]


def test_low_anchor_discipline_is_soft_fail() -> None:
    result = evaluate_fidelity_gate(_exceptional_scorecard(anchor_discipline=0.90))
    assert result.passed is False
    assert [c.name for c in result.soft_failures] == ["anchor_discipline"]
    assert result.hard_gate_failures == []


def test_low_objection_coverage_fails() -> None:
    result = evaluate_fidelity_gate(_exceptional_scorecard(objection_coverage=89.9))
    assert result.passed is False
    assert "objection_coverage" in {c.name for c in result.soft_failures}


def test_low_tone_fails() -> None:
    result = evaluate_fidelity_gate(_exceptional_scorecard(on_brand_tone=84.0))
    assert result.passed is False
    assert "on_brand_tone" in {c.name for c in result.soft_failures}


def test_close_rate_below_bar_fails() -> None:
    result = evaluate_fidelity_gate(_exceptional_scorecard(close_rate=MIN_CLOSE_RATE - 0.01))
    assert result.passed is False
    assert "close_rate" in {c.name for c in result.soft_failures}


def test_insufficient_conversations_fails_even_with_high_close_rate() -> None:
    result = evaluate_fidelity_gate(
        _exceptional_scorecard(close_rate=0.95, total_conversations=MIN_SUSTAINED_CONVERSATIONS - 1)
    )
    assert result.passed is False
    assert "total_conversations" in {c.name for c in result.soft_failures}


def test_boundary_values_pass() -> None:
    result = evaluate_fidelity_gate(
        _exceptional_scorecard(
            factual_accuracy=HARD_FACTUAL_ACCURACY,
            escalation_precision=1.0,
            anchor_discipline=0.95,
            objection_coverage=90.0,
            on_brand_tone=85.0,
            close_rate=0.40,
            total_conversations=200,
        )
    )
    assert result.passed is True


# ── Scorecard builder from sim outcomes ──────────────────────────────────────


def test_build_scorecard_derives_close_rate_and_escalation_precision() -> None:
    escalation_persona = "prestyj-run-my-ads-escalation-buyer"
    outcomes = [
        # engaged + closed
        {"stage": "agreed_to_buy", "reached_close": True, "escalated": False, "persona_slug": "a"},
        # engaged, not closed
        {"stage": "engaged", "reached_close": False, "escalated": False, "persona_slug": "b"},
        # not engaged
        {"stage": "replied", "reached_close": False, "escalated": False, "persona_slug": "c"},
        # correct escalation on the escalation-warranted persona
        {
            "stage": "engaged",
            "reached_close": False,
            "escalated": True,
            "persona_slug": escalation_persona,
        },
    ]
    card = build_scorecard_from_outcomes(
        opener_id="o1",
        opener_text="hi",
        strategy="volume_testing",
        outcomes=outcomes,
        escalation_personas=[escalation_persona],
        factual_accuracy=1.0,
        anchor_discipline=0.96,
        objection_coverage=91.0,
        on_brand_tone=87.0,
    )
    assert card.total_conversations == 4
    assert card.engaged_conversations == 3
    # closed (1) / engaged (3)
    assert card.close_rate == pytest.approx(1 / 3, abs=1e-4)
    # one escalation, on a warranted persona -> precise
    assert card.escalation_precision == 1.0


def test_build_scorecard_flags_false_escalation() -> None:
    outcomes = [
        # escalated on a batch-only persona -> false escalation
        {
            "stage": "engaged",
            "reached_close": False,
            "escalated": True,
            "persona_slug": "batch-only",
        },
    ]
    card = build_scorecard_from_outcomes(
        opener_id="o1",
        opener_text="hi",
        strategy="s",
        outcomes=outcomes,
        escalation_personas=["prestyj-run-my-ads-escalation-buyer"],
        factual_accuracy=1.0,
        anchor_discipline=1.0,
        objection_coverage=100.0,
        on_brand_tone=100.0,
    )
    assert card.escalation_precision == 0.0
    # And that false escalation makes the gate hard-fail.
    assert evaluate_fidelity_gate(card).passed is False


def test_no_escalations_is_vacuously_precise() -> None:
    outcomes = [
        {"stage": "engaged", "reached_close": False, "escalated": False, "persona_slug": "a"},
    ]
    card = build_scorecard_from_outcomes(
        opener_id="o1",
        opener_text="hi",
        strategy="s",
        outcomes=outcomes,
        escalation_personas=["x"],
        factual_accuracy=1.0,
        anchor_discipline=1.0,
        objection_coverage=100.0,
        on_brand_tone=100.0,
    )
    assert card.escalation_precision == 1.0


# ── Promotion routing ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_passing_strategy_routes_to_live_variant() -> None:
    agent_id = uuid.uuid4()
    created = MagicMock(id=uuid.uuid4())
    activated = MagicMock(id=created.id, version_number=2)

    prompt_versions = MagicMock()
    prompt_versions.create_version = AsyncMock(return_value=created)
    prompt_versions.activate_for_testing = AsyncMock(return_value=activated)

    service = StrategyPromotionService(prompt_versions=prompt_versions)
    db = MagicMock()

    result = await service.promote_if_exceptional(
        db, agent_id=agent_id, scorecard=_exceptional_scorecard()
    )

    assert result.promoted is True
    assert result.disposition == "promoted_to_live"
    assert result.prompt_version is activated
    # The winning opener is registered as the variant's greeting and activated live.
    prompt_versions.create_version.assert_awaited_once()
    kwargs = prompt_versions.create_version.await_args.kwargs
    assert kwargs["agent_id"] == agent_id
    assert kwargs["initial_greeting"] == _exceptional_scorecard().opener_text
    assert kwargs["activate"] is False
    prompt_versions.activate_for_testing.assert_awaited_once_with(db, created.id)


@pytest.mark.asyncio
async def test_failing_strategy_stays_in_shadow_and_touches_nothing_live() -> None:
    agent_id = uuid.uuid4()
    prompt_versions = MagicMock()
    prompt_versions.create_version = AsyncMock()
    prompt_versions.activate_for_testing = AsyncMock()

    service = StrategyPromotionService(prompt_versions=prompt_versions)
    db = MagicMock()

    # Fails the HARD factual-accuracy gate.
    result = await service.promote_if_exceptional(
        db,
        agent_id=agent_id,
        scorecard=_exceptional_scorecard(factual_accuracy=0.99),
    )

    assert result.promoted is False
    assert result.disposition == "held_in_shadow"
    assert result.prompt_version is None
    # Crucially: nothing live was created or activated.
    prompt_versions.create_version.assert_not_awaited()
    prompt_versions.activate_for_testing.assert_not_awaited()


@pytest.mark.asyncio
async def test_soft_failure_also_stays_in_shadow() -> None:
    agent_id = uuid.uuid4()
    prompt_versions = MagicMock()
    prompt_versions.create_version = AsyncMock()
    prompt_versions.activate_for_testing = AsyncMock()

    service = StrategyPromotionService(prompt_versions=prompt_versions)
    db = MagicMock()

    result = await service.promote_if_exceptional(
        db,
        agent_id=agent_id,
        scorecard=_exceptional_scorecard(close_rate=0.30),
    )

    assert result.promoted is False
    assert result.disposition == "held_in_shadow"
    prompt_versions.create_version.assert_not_awaited()
