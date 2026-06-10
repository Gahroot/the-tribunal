"""Streaming (during-call) sentiment scoring for live voice calls.

Unlike :mod:`app.services.ai.transcript_analysis`, which runs a single LLM
pass over the *finished* transcript after the call, this module scores the
caller's sentiment incrementally as each utterance is transcribed. It is
deliberately lexicon-based (no network round-trip) so it adds no latency to
the live audio path and is fully deterministic for testing.

The scorer maintains an exponentially-weighted moving average (EWMA) of
per-utterance scores plus a run-length of consecutive negative turns. When
negative sentiment is *sustained* (EWMA at/below the configured escalation
threshold AND a minimum number of consecutive negative turns), it emits a
one-shot escalation signal that the voice bridge turns into an operator
notification and (optionally) an automatic human transfer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "SentimentUpdate",
    "LiveSentimentScorer",
    "score_utterance",
    "classify_score",
]

# Lexicon-based scoring. Kept intentionally small and high-signal so the score
# reflects clear emotional language rather than every filler word. Phrases are
# matched on word boundaries (case-insensitive).
_NEGATIVE_TERMS: frozenset[str] = frozenset(
    {
        "angry",
        "annoyed",
        "annoying",
        "awful",
        "cancel",
        "complaint",
        "disappointed",
        "disgusted",
        "frustrated",
        "frustrating",
        "furious",
        "garbage",
        "hate",
        "horrible",
        "lawyer",
        "lawsuit",
        "mad",
        "nonsense",
        "pathetic",
        "pissed",
        "ridiculous",
        "refund",
        "scam",
        "stupid",
        "terrible",
        "unacceptable",
        "unhappy",
        "upset",
        "useless",
        "worst",
        "wtf",
    }
)

# Multi-word negative phrases scored as a single hit.
_NEGATIVE_PHRASES: tuple[str, ...] = (
    "fed up",
    "waste of time",
    "wasting my time",
    "speak to a manager",
    "speak to a human",
    "talk to a person",
    "not good enough",
    "this is a joke",
    "give me my money back",
    "never again",
    "no help",
    "doesn't work",
    "does not work",
    "not working",
)

_POSITIVE_TERMS: frozenset[str] = frozenset(
    {
        "amazing",
        "appreciate",
        "awesome",
        "brilliant",
        "excellent",
        "fantastic",
        "glad",
        "good",
        "great",
        "happy",
        "helpful",
        "love",
        "lovely",
        "nice",
        "perfect",
        "pleased",
        "thank",
        "thanks",
        "wonderful",
    }
)

_POSITIVE_PHRASES: tuple[str, ...] = (
    "thank you",
    "really helpful",
    "sounds good",
    "that works",
    "much appreciated",
)

# Negators that flip the polarity of an adjacent sentiment term.
_NEGATORS: frozenset[str] = frozenset({"not", "no", "never", "isn't", "wasn't", "don't", "can't"})

_WORD_RE = re.compile(r"[a-z']+")

# Default classification band: scores above POSITIVE_BAND are "positive", below
# NEGATIVE_BAND are "negative", otherwise "neutral".
POSITIVE_BAND = 0.15
NEGATIVE_BAND = -0.15


def classify_score(score: float) -> str:
    """Map a numeric sentiment score in [-1, 1] to a label."""
    if score > POSITIVE_BAND:
        return "positive"
    if score < NEGATIVE_BAND:
        return "negative"
    return "neutral"


def _count_token_hits(tokens: list[str]) -> tuple[int, int]:
    """Count positive/negative single-word hits, applying adjacent negation."""
    positive_hits = 0
    negative_hits = 0
    for idx, token in enumerate(tokens):
        negated = idx > 0 and tokens[idx - 1] in _NEGATORS
        if token in _NEGATIVE_TERMS:
            target = "pos" if negated else "neg"
        elif token in _POSITIVE_TERMS:
            target = "neg" if negated else "pos"
        else:
            continue
        if target == "pos":
            positive_hits += 1
        else:
            negative_hits += 1
    return positive_hits, negative_hits


def score_utterance(text: str) -> float:
    """Score a single utterance, returning a value in [-1.0, 1.0].

    Returns 0.0 (neutral) when no sentiment-bearing terms are present. A simple
    adjacent-negator rule flips polarity for phrases like "not great".
    """
    if not text:
        return 0.0

    lowered = text.lower()

    # Phrase matches first (substring, since phrases include spaces).
    negative_hits = sum(1 for phrase in _NEGATIVE_PHRASES if phrase in lowered)
    positive_hits = sum(1 for phrase in _POSITIVE_PHRASES if phrase in lowered)

    token_pos, token_neg = _count_token_hits(_WORD_RE.findall(lowered))
    positive_hits += token_pos
    negative_hits += token_neg

    total = positive_hits + negative_hits
    if total == 0:
        return 0.0

    return (positive_hits - negative_hits) / total


@dataclass(frozen=True)
class SentimentUpdate:
    """Result of feeding one utterance to :class:`LiveSentimentScorer`.

    Attributes:
        utterance_score: Raw score for this single utterance ([-1, 1]).
        score: Smoothed running sentiment score (EWMA) for the call.
        sentiment: Label for ``score`` ("positive" | "neutral" | "negative").
        consecutive_negative: Run-length of consecutive negative utterances.
        escalate: True exactly once, on the turn sustained negativity crosses
            the configured threshold. Subsequent updates report False.
        turns: Number of utterances scored so far (including this one).
    """

    utterance_score: float
    score: float
    sentiment: str
    consecutive_negative: int
    escalate: bool
    turns: int


class LiveSentimentScorer:
    """Incremental sentiment tracker with sustained-negativity escalation.

    Args:
        negative_threshold: Smoothed score at/below which sentiment counts as
            sustained-negative for escalation. Also used as the per-utterance
            "negative turn" cutoff. Expected in [-1, 0).
        sustained_turns: Number of consecutive negative utterances required
            (in addition to the smoothed score crossing the threshold) before
            escalation fires. Must be >= 1.
        smoothing: EWMA smoothing factor in (0, 1]. Higher reacts faster to the
            latest utterance; lower is steadier.
    """

    def __init__(
        self,
        *,
        negative_threshold: float = -0.4,
        sustained_turns: int = 3,
        smoothing: float = 0.5,
    ) -> None:
        if not 0.0 < smoothing <= 1.0:
            raise ValueError("smoothing must be in (0, 1]")
        if sustained_turns < 1:
            raise ValueError("sustained_turns must be >= 1")

        self.negative_threshold = negative_threshold
        self.sustained_turns = sustained_turns
        self.smoothing = smoothing

        self._score: float = 0.0
        self._turns: int = 0
        self._consecutive_negative: int = 0
        self._escalated: bool = False

    @property
    def score(self) -> float:
        """Current smoothed sentiment score."""
        return self._score

    @property
    def sentiment(self) -> str:
        """Current smoothed sentiment label."""
        return classify_score(self._score)

    @property
    def escalated(self) -> bool:
        """Whether escalation has already fired for this call."""
        return self._escalated

    def add_utterance(self, text: str) -> SentimentUpdate:
        """Score a caller utterance and update running state."""
        utterance_score = score_utterance(text)

        self._turns += 1
        if self._turns == 1:
            self._score = utterance_score
        else:
            self._score = self.smoothing * utterance_score + (1.0 - self.smoothing) * self._score

        # A turn counts as "negative" when its own score is at/below the
        # threshold; a clearly non-negative turn resets the streak.
        if utterance_score <= self.negative_threshold:
            self._consecutive_negative += 1
        else:
            self._consecutive_negative = 0

        escalate = False
        if (
            not self._escalated
            and self._consecutive_negative >= self.sustained_turns
            and self._score <= self.negative_threshold
        ):
            escalate = True
            self._escalated = True

        return SentimentUpdate(
            utterance_score=utterance_score,
            score=self._score,
            sentiment=classify_score(self._score),
            consecutive_negative=self._consecutive_negative,
            escalate=escalate,
            turns=self._turns,
        )
