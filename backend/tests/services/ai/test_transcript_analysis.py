"""Tests for transcript analysis service."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.ai import transcript_analysis


def _make_response(payload: dict[str, object]) -> SimpleNamespace:
    message = SimpleNamespace(content=json.dumps(payload))
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


@pytest.mark.asyncio
async def test_analyze_transcript_returns_normalized_dict() -> None:
    payload = {
        "sentiment": "positive",
        "sentiment_score": 0.8,
        "intents": ["book_appointment", "learn_pricing"],
        "topics": ["pricing", "availability"],
        "summary": "Caller wants to book a consult.",
        "objections": ["budget"],
        "next_steps": ["send quote"],
    }
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value=_make_response(payload)))
        )
    )

    with patch.object(transcript_analysis, "_get_client", return_value=fake_client):
        result = await transcript_analysis.analyze_transcript("hello world")

    assert result["sentiment"] == "positive"
    assert result["sentiment_score"] == pytest.approx(0.8)
    assert result["intents"] == ["book_appointment", "learn_pricing"]
    assert result["topics"] == ["pricing", "availability"]
    assert result["summary"] == "Caller wants to book a consult."
    assert result["objections"] == ["budget"]
    assert result["next_steps"] == ["send quote"]


@pytest.mark.asyncio
async def test_analyze_transcript_normalizes_bad_values() -> None:
    payload = {
        "sentiment": "ecstatic",
        "sentiment_score": "not a number",
        "intents": "nope",
        "summary": None,
    }
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value=_make_response(payload)))
        )
    )

    with patch.object(transcript_analysis, "_get_client", return_value=fake_client):
        result = await transcript_analysis.analyze_transcript("hi")

    assert result["sentiment"] == "neutral"
    assert result["sentiment_score"] == 0.0
    assert result["intents"] == []
    assert result["topics"] == []
    assert result["objections"] == []
    assert result["next_steps"] == []
    assert result["summary"] == "None"


@pytest.mark.asyncio
async def test_analyze_transcript_clamps_score() -> None:
    payload = {"sentiment": "negative", "sentiment_score": -9.0}
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value=_make_response(payload)))
        )
    )
    with patch.object(transcript_analysis, "_get_client", return_value=fake_client):
        result = await transcript_analysis.analyze_transcript("text")
    assert result["sentiment_score"] == -1.0
