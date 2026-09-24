"""SMS output and tool arguments must not accept malformed model content."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from app.services.ai.text_response_generator import _validated_text
from app.services.ai.text_tool_executor import TextToolExecutor


@pytest.mark.asyncio
async def test_text_output_retries_blank_response() -> None:
    attempts = 0

    def respond(messages, info):
        nonlocal attempts
        attempts += 1
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {"text": "  " if attempts == 1 else "Hello, how can I help?"},
                )
            ]
        )

    with (
        patch(
            "app.services.ai.structured_output.OpenAIChatModel", return_value=FunctionModel(respond)
        ),
        patch("app.services.ai.structured_output.OpenAIProvider", return_value=object()),
    ):
        result = await _validated_text(
            object(),
            "Be helpful",
            [{"role": "user", "content": "Hi"}],
            temperature=0.3,
            max_tokens=200,
            timeout=30,
        )
    assert attempts == 2
    assert result == "Hello, how can I help?"


@pytest.mark.asyncio
async def test_text_output_fails_after_exhausting_corrections() -> None:
    def respond(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"text": " "})])

    with (
        patch(
            "app.services.ai.structured_output.OpenAIChatModel", return_value=FunctionModel(respond)
        ),
        patch("app.services.ai.structured_output.OpenAIProvider", return_value=object()),
        pytest.raises(UnexpectedModelBehavior),
    ):
        await _validated_text(
            object(),
            "Be helpful",
            [{"role": "user", "content": "Hi"}],
            temperature=0.3,
            max_tokens=200,
            timeout=30,
        )


@pytest.mark.asyncio
async def test_invalid_tool_arguments_never_reach_approval() -> None:
    executor = object.__new__(TextToolExecutor)
    executor.log = SimpleNamespace(info=lambda *args, **kwargs: None)
    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="book_appointment", arguments='{"date":"today"}'),
    )
    with (
        patch(
            "app.services.ai.text_tool_executor.approval_gate_service.check_and_execute_or_queue",
            new_callable=AsyncMock,
        ) as approval,
        pytest.raises(ValidationError),
    ):
        await executor.handle_tool_calls([tool_call])
    approval.assert_not_awaited()
