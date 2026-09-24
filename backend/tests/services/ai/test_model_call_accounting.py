"""Every paid structured-output attempt must retain its own model and usage."""

from decimal import Decimal
from unittest.mock import patch

import pytest
from pydantic import BaseModel
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from app.services.ai.model_config import Selection
from app.services.ai.structured_output import generate_structured


class Answer(BaseModel):
    count: int


@pytest.mark.asyncio
@pytest.mark.parametrize("exhaust_retries", [False, True])
async def test_each_response_is_logged_even_when_validation_exhausts_retries(
    exhaust_retries: bool,
) -> None:
    attempts = 0

    def respond(messages, info):
        nonlocal attempts
        attempts += 1
        value = "invalid" if exhaust_retries or attempts == 1 else 2
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"count": value})],
            model_name="gpt-test-snapshot",
            usage=RequestUsage(input_tokens=100, output_tokens=20),
        )

    with (
        patch(
            "app.services.ai.structured_output.OpenAIChatModel",
            return_value=FunctionModel(respond, model_name="gpt-test-snapshot"),
        ),
        patch("app.services.ai.structured_output.OpenAIProvider", return_value=object()),
        patch("app.services.ai.model_config.structlog.get_logger") as logger,
    ):

        async def run():
            return await generate_structured(
                client=object(),
                model="gpt-test",
                schema=Answer,
                system_prompt="Count.",
                user_prompt="Two.",
                selection=Selection("gpt-test", Decimal("1"), Decimal("2")),
                task="reports",
            )

        if exhaust_retries:
            with pytest.raises(UnexpectedModelBehavior):
                await run()
        else:
            assert (await run()).count == 2

        events = [call.kwargs for call in logger.return_value.info.call_args_list]
        assert len(events) == attempts == (3 if exhaust_retries else 2)
        for event in events:
            assert event["task"] == "reports"
            assert event["model"] == "gpt-test-snapshot"
            assert event["input_tokens"] == 100
            assert event["output_tokens"] == 20
            assert event["cost_usd"] == "0.00014"
