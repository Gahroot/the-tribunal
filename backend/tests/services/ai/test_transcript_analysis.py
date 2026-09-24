"""Regression tests for validated transcript outputs."""

from unittest.mock import patch

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from app.services.ai import transcript_analysis


@pytest.mark.asyncio
async def test_transcript_retries_invalid_output_then_accepts_correction() -> None:
    attempts = 0

    def respond(messages, info):
        nonlocal attempts
        attempts += 1
        assert info.output_tools
        payload = {
            "sentiment": "positive",
            "sentiment_score": 0.8,
            "intents": ["book_appointment"],
            "topics": ["pricing"],
            "summary": "Caller wants a consult.",
            "objections": [],
            "next_steps": ["send quote"],
            "preferred_call_time": None,
            "callback_promise": None,
        }
        if attempts == 1:
            payload["sentiment"] = "ecstatic"
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, payload)])

    model = FunctionModel(respond)
    with (
        patch.object(transcript_analysis, "_get_client", return_value=object()),
        patch("app.services.ai.structured_output.OpenAIChatModel", return_value=model),
        patch("app.services.ai.structured_output.OpenAIProvider", return_value=object()),
    ):
        result = await transcript_analysis.analyze_transcript("hello world")
    assert attempts == 2
    assert result["sentiment"] == "positive"
    assert result["summary"] == "Caller wants a consult."


@pytest.mark.asyncio
async def test_transcript_rejects_persistent_invalid_output() -> None:
    def respond(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"sentiment": "bad"})])

    with (
        patch.object(transcript_analysis, "_get_client", return_value=object()),
        patch(
            "app.services.ai.structured_output.OpenAIChatModel",
            return_value=FunctionModel(respond),
        ),
        patch("app.services.ai.structured_output.OpenAIProvider", return_value=object()),
        pytest.raises(UnexpectedModelBehavior),
    ):
        await transcript_analysis.analyze_transcript("hello world")
