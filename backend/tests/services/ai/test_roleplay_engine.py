"""Unit tests for the practice-arena roleplay engine.

These cover the pure / LLM-boundary pieces (prospect simulator, agent responder,
report scorer, default personas) with mocked OpenAI clients — no real DB or
network. They prove transcript mapping, JSON score parsing/clamping, and
graceful fallbacks.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ai.roleplay import DEFAULT_PERSONAS
from app.services.ai.roleplay.agent_responder import (
    _build_messages as build_agent_messages,
)
from app.services.ai.roleplay.agent_responder import generate_agent_reply
from app.services.ai.roleplay.prospect_simulator import (
    _build_messages as build_prospect_messages,
)
from app.services.ai.roleplay.prospect_simulator import generate_prospect_reply
from app.services.ai.roleplay.report_scorer import score_rehearsal


def _mock_client(content: str) -> MagicMock:
    """Build a fake AsyncOpenAI whose completion returns ``content``."""
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    response = SimpleNamespace(choices=[choice])
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


SAMPLE_TRANSCRIPT = [
    {"role": "prospect", "content": "Who is this?"},
    {"role": "agent", "content": "Hi! I'm reaching out about your roof estimate."},
    {"role": "prospect", "content": "Sounds expensive."},
]


class TestTranscriptMapping:
    def test_prospect_perspective_flips_roles(self) -> None:
        messages = build_prospect_messages("persona", SAMPLE_TRANSCRIPT)
        assert messages[0] == {"role": "system", "content": "persona"}
        # Prospect's own lines are assistant; agent lines are user.
        assert messages[1]["role"] == "assistant"
        assert messages[2]["role"] == "user"
        assert messages[3]["role"] == "assistant"

    def test_agent_perspective_flips_roles(self) -> None:
        messages = build_agent_messages("sys", SAMPLE_TRANSCRIPT)
        assert messages[0]["role"] == "system"
        # Agent's own lines are assistant; prospect lines are user.
        assert messages[1]["role"] == "user"
        assert messages[2]["role"] == "assistant"
        assert messages[3]["role"] == "user"


class TestProspectSimulator:
    async def test_returns_model_text(self) -> None:
        client = _mock_client("I'm not interested, sorry.")
        reply = await generate_prospect_reply(
            client=client, persona_prompt="be skeptical", transcript=SAMPLE_TRANSCRIPT
        )
        assert reply == "I'm not interested, sorry."

    async def test_falls_back_on_error(self) -> None:
        client = MagicMock()
        client.chat.completions.create = AsyncMock(side_effect=RuntimeError("boom"))
        reply = await generate_prospect_reply(
            client=client, persona_prompt="be skeptical", transcript=[]
        )
        assert reply  # non-empty fallback, no exception raised


class TestAgentResponder:
    async def test_returns_model_text(self) -> None:
        client = _mock_client("Happy to explain the pricing!")
        reply = await generate_agent_reply(
            client=client, system_prompt="you are a rep", transcript=SAMPLE_TRANSCRIPT
        )
        assert reply == "Happy to explain the pricing!"


class TestReportScorer:
    async def test_parses_and_clamps_scores(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.services.ai.roleplay.report_scorer.analyze_transcript",
            AsyncMock(return_value={"sentiment": "neutral", "summary": "ok"}),
        )
        payload = {
            "overall_score": 150,  # should clamp to 100
            "objection_coverage_score": -5,  # should clamp to 0
            "tone_score": 72.5,
            "tone_label": "warm",
            "booking_attempted": True,
            "objection_breakdown": [
                {"objection": "price", "addressed": True, "note": "handled well"}
            ],
            "summary": "Solid rapport.",
            "strengths": ["clear", "friendly"],
            "gaps": ["no urgency"],
            "suggestions": ["add pricing to knowledge base"],
        }
        client = _mock_client(json.dumps(payload))

        report = await score_rehearsal(
            client=client,
            transcript=SAMPLE_TRANSCRIPT,
            persona_name="Skeptical Homeowner",
            objections=["price"],
            goal="book a visit",
        )

        assert report.overall_score == 100.0
        assert report.objection_coverage == 0.0
        assert report.tone_score == 72.5
        assert report.booking_attempted is True
        assert report.summary == "Solid rapport."
        assert report.strengths == ["clear", "friendly"]
        assert report.suggestions == ["add pricing to knowledge base"]
        assert report.scores["tone_label"] == "warm"
        assert report.scores["objection_breakdown"][0]["objection"] == "price"
        assert report.scores["sentiment"] == "neutral"

    async def test_invalid_json_yields_valid_zero_report(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.services.ai.roleplay.report_scorer.analyze_transcript",
            AsyncMock(return_value={}),
        )
        client = _mock_client("not json at all")
        report = await score_rehearsal(
            client=client,
            transcript=SAMPLE_TRANSCRIPT,
            persona_name="Prospect",
            objections=[],
            goal=None,
        )
        assert report.overall_score == 0.0
        assert report.booking_attempted is False
        assert report.strengths == []


class TestDefaultPersonas:
    def test_three_builtins_with_required_fields(self) -> None:
        slugs = {p.slug for p in DEFAULT_PERSONAS}
        assert {
            "skeptical-homeowner",
            "price-shopping-patient",
            "budget-conscious-solar-lead",
        } <= slugs
        for persona in DEFAULT_PERSONAS:
            assert persona.persona_prompt
            assert persona.opening_message
            assert persona.objections  # each ships with concrete objections
