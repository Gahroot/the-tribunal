"""Validated OpenAI outputs with bounded, model-visible correction attempts."""

from collections.abc import Callable
from types import SimpleNamespace

from openai import AsyncOpenAI
from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from app.services.ai.model_config import Selection, Task, log_model_usage


class _UsageLoggedModel(WrapperModel):
    """Log each response before validation, including paid correction attempts."""

    def __init__(self, wrapped: Model, selection: Selection, task: Task) -> None:
        super().__init__(wrapped)
        self.selection = selection
        self.task = task

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        response = await self.wrapped.request(messages, model_settings, model_request_parameters)
        log_model_usage(
            self.task,
            self.selection,
            SimpleNamespace(
                model=response.model_name,
                usage=SimpleNamespace(
                    prompt_tokens=response.usage.input_tokens,
                    completion_tokens=response.usage.output_tokens,
                ),
            ),
        )
        return response


async def generate_structured[Output: BaseModel](
    *,
    client: AsyncOpenAI,
    model: str,
    schema: type[Output],
    system_prompt: str,
    user_prompt: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: float | None = None,
    seed: int | None = None,
    selection: Selection | None = None,
    task: Task | None = None,
    validate: Callable[[Output], None] | None = None,
) -> Output:
    """Reject malformed data, retry through the model, and propagate exhausted retries."""
    chat_model: Model = OpenAIChatModel(model, provider=OpenAIProvider(openai_client=client))
    if selection is not None and task is not None:
        chat_model = _UsageLoggedModel(chat_model, selection, task)
    agent = Agent(
        chat_model,
        output_type=schema,
        retries=2,
        system_prompt=system_prompt,
    )

    @agent.output_validator
    def check_output(output: Output) -> Output:
        # Pydantic validates the shape; model validators may additionally reject
        # cross-field inconsistencies with a ValueError/ValidationError.
        if validate is not None:
            try:
                validate(output)
            except ValueError as exc:
                raise ModelRetry(str(exc)) from exc
        return output

    settings = ModelSettings()
    if temperature is not None:
        settings["temperature"] = temperature
    if max_tokens is not None:
        settings["max_tokens"] = max_tokens
    if timeout is not None:
        settings["timeout"] = timeout
    if seed is not None:
        settings["seed"] = seed
    result = await agent.run(user_prompt, model_settings=settings)
    return result.output
