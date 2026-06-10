"""Tests for streaming (during-call) sentiment scoring + escalation."""

import pytest

from app.services.ai.live_sentiment import (
    LiveSentimentScorer,
    classify_score,
    score_utterance,
)

NEG = "This is terrible and awful, absolutely the worst."
POS = "This is great, thank you so much, really helpful!"
NEUTRAL = "I called about my appointment on Tuesday."


def test_score_utterance_polarity() -> None:
    assert score_utterance(NEG) < -0.5
    assert score_utterance(POS) > 0.5
    assert score_utterance(NEUTRAL) == 0.0
    assert score_utterance("") == 0.0


def test_score_utterance_handles_negation() -> None:
    # "not great" should read negative, not positive.
    assert score_utterance("this is not great at all") < 0.0
    # "not terrible" should read positive (flipped).
    assert score_utterance("honestly it's not terrible") > 0.0


def test_classify_score_bands() -> None:
    assert classify_score(0.9) == "positive"
    assert classify_score(0.0) == "neutral"
    assert classify_score(-0.9) == "negative"


def test_escalation_fires_after_sustained_negative_turns() -> None:
    scorer = LiveSentimentScorer(negative_threshold=-0.4, sustained_turns=3, smoothing=0.5)

    u1 = scorer.add_utterance(NEG)
    assert u1.escalate is False
    assert u1.consecutive_negative == 1
    assert u1.sentiment == "negative"

    u2 = scorer.add_utterance(NEG)
    assert u2.escalate is False
    assert u2.consecutive_negative == 2

    # Third consecutive negative turn crosses the threshold -> escalate.
    u3 = scorer.add_utterance(NEG)
    assert u3.escalate is True
    assert u3.consecutive_negative == 3
    assert u3.score <= -0.4


def test_escalation_is_one_shot() -> None:
    scorer = LiveSentimentScorer(negative_threshold=-0.4, sustained_turns=2, smoothing=0.5)
    scorer.add_utterance(NEG)
    assert scorer.add_utterance(NEG).escalate is True
    # Already escalated: subsequent negative turns do not re-fire.
    assert scorer.add_utterance(NEG).escalate is False
    assert scorer.escalated is True


def test_positive_turn_resets_negative_streak() -> None:
    scorer = LiveSentimentScorer(negative_threshold=-0.4, sustained_turns=3, smoothing=0.5)
    scorer.add_utterance(NEG)
    scorer.add_utterance(NEG)
    # A positive turn resets the consecutive-negative counter.
    reset = scorer.add_utterance(POS)
    assert reset.consecutive_negative == 0
    # Two more negatives are not enough to reach sustained_turns=3 again.
    assert scorer.add_utterance(NEG).escalate is False
    assert scorer.add_utterance(NEG).escalate is False


def test_no_escalation_when_below_sustained_count() -> None:
    scorer = LiveSentimentScorer(negative_threshold=-0.4, sustained_turns=5, smoothing=0.5)
    for _ in range(4):
        assert scorer.add_utterance(NEG).escalate is False
    assert scorer.escalated is False


def test_invalid_config_rejected() -> None:
    with pytest.raises(ValueError):
        LiveSentimentScorer(smoothing=0.0)
    with pytest.raises(ValueError):
        LiveSentimentScorer(smoothing=1.5)
    with pytest.raises(ValueError):
        LiveSentimentScorer(sustained_turns=0)
