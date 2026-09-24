"""Offline rubric fixtures and reward boundaries (no external LLM dependency)."""

import pytest

from app.services.ai.call_judge import CRITERIA, validate_judgment
from app.services.ai.reward_config import compute_call_reward

TRANSCRIPT = "Agent: Hello. Prospect: I need a house. Agent: I hear you."


def judgment(score: int = 4, quote: str = "Agent: Hello.") -> dict:
    return {
        **{name: {"score": score, "quote": quote} for name in CRITERIA},
        "confidence": 0.9,
        "human_review": False,
    }


def test_rubric_evidence_and_score():
    result = validate_judgment(judgment(), TRANSCRIPT)
    assert result["score"] == 1
    assert result["human_review"] is False
    assert set(result["scores"]) == set(CRITERIA)
    assert all(result["scores"][key]["quote"] == "Agent: Hello." for key in CRITERIA)


def test_unverifiable_evidence_rejected():
    with pytest.raises(ValueError, match="Unverifiable evidence"):
        validate_judgment(judgment(quote="Fake booking"), TRANSCRIPT)


def test_low_confidence_or_compliance_requires_review():
    low = judgment()
    low["confidence"] = 0.4
    assert validate_judgment(low, TRANSCRIPT)["human_review"] is True
    unsafe = judgment()
    unsafe["compliance"]["score"] = 1
    assert validate_judgment(unsafe, TRANSCRIPT)["human_review"] is True


def test_outcome_quality_duration_all_contribute():
    quality = {"score": 1.0}
    good = compute_call_reward("appointment_booked", {}, quality, 120)
    assert good == pytest.approx(1.0)
    assert compute_call_reward("failed", {}, quality, 120) < good
    assert compute_call_reward("appointment_booked", {}, None, 120) < good
    assert compute_call_reward("appointment_booked", {}, quality, 10) < good
    assert compute_call_reward("failed", {}, None, None) == 0


def test_invalid_agent_reward_weights_fail_closed():
    with pytest.raises(ValueError, match="Invalid bandit reward weight"):
        compute_call_reward("completed", {}, None, 10, {"quality_weight": -1})
    with pytest.raises(ValueError, match="must not all be zero"):
        compute_call_reward(
            "completed",
            {},
            None,
            10,
            {"outcome_weight": 0, "quality_weight": 0, "duration_weight": 0},
        )
