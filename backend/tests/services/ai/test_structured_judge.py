"""Judge evidence is checked during the model's correction loop."""

from unittest.mock import patch

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from app.services.ai.call_judge import judge_call


@pytest.mark.asyncio
async def test_judge_retries_fabricated_quote_before_accepting_verifiable_evidence() -> None:
    attempts = 0

    def respond(messages, info):
        nonlocal attempts
        attempts += 1
        evidence = "Made-up promise" if attempts == 1 else "I can book a call"
        payload = {
            category: {"score": 3, "quote": evidence}
            for category in ("opening", "listening", "objection_handling", "compliance", "close")
        }
        payload.update({"confidence": 0.8, "human_review": False})
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, payload)])

    with (
        patch("app.services.ai.call_judge.create_openai_client", return_value=object()),
        patch(
            "app.services.ai.structured_output.OpenAIChatModel", return_value=FunctionModel(respond)
        ),
        patch("app.services.ai.structured_output.OpenAIProvider", return_value=object()),
    ):
        result = await judge_call("Agent: I can book a call")
    assert attempts == 2
    assert result["scores"]["opening"]["quote"] == "I can book a call"


@pytest.mark.asyncio
async def test_judge_fails_after_repeated_fabricated_evidence() -> None:
    def respond(messages, info):
        payload = {
            category: {"score": 3, "quote": "Unspoken quote"}
            for category in ("opening", "listening", "objection_handling", "compliance", "close")
        }
        payload.update({"confidence": 0.8, "human_review": False})
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, payload)])

    with (
        patch("app.services.ai.call_judge.create_openai_client", return_value=object()),
        patch(
            "app.services.ai.structured_output.OpenAIChatModel", return_value=FunctionModel(respond)
        ),
        patch("app.services.ai.structured_output.OpenAIProvider", return_value=object()),
        pytest.raises(UnexpectedModelBehavior),
    ):
        await judge_call("Agent: I can book a call")
