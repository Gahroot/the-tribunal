"""Exercise the real agent validation/retry loop without network calls.

Malformed JSON must be corrected by the model, never salvaged locally. Stored
transcript JSON, transport frames, and executor-produced JSON are not LLM output.
"""

import json
from unittest.mock import patch

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from app.services.ai.call_judge import CRITERIA, judge_call
from app.services.ai.caller_memory_service import summarize_call_transcript
from app.services.ai.text_response_generator import _validated_text
from app.services.ai.transcript_analysis import analyze_transcript

TRANSCRIPT = "Caller: Please call tomorrow."
PAYLOADS = {
    "transcript": {
        "sentiment": "neutral",
        "sentiment_score": 0.0,
        "intents": ["callback"],
        "topics": [],
        "summary": "Caller requested a callback.",
        "objections": [],
        "next_steps": ["Call tomorrow"],
        "preferred_call_time": "tomorrow",
        "callback_promise": None,
    },
    "memory": {"summary": "Caller requested a callback tomorrow."},
    "text": {"text": "What time tomorrow works for you?"},
    "judge": {
        **{category: {"score": 3, "quote": "Please call tomorrow."} for category in CRITERIA},
        "confidence": 0.8,
        "human_review": False,
    },
}


async def run_service(service):
    if service == "transcript":
        return await analyze_transcript(TRANSCRIPT)
    if service == "memory":
        return await summarize_call_transcript(TRANSCRIPT)
    if service == "judge":
        return await judge_call(TRANSCRIPT)
    return await _validated_text(
        object(),
        "Be helpful",
        [{"role": "user", "content": TRANSCRIPT}],
        temperature=0.2,
        max_tokens=500,
        timeout=30,
    )


def invalid_payload(service, defect):
    payload = PAYLOADS[service]
    if defect == "truncated":
        return json.dumps(payload)[:-1]
    if defect == "fenced":
        return "```json\n" + json.dumps(payload) + "\n```"
    if defect == "missing":
        return "{}"
    if defect == "extra":
        return json.dumps({**payload, "unexpected": True})
    field = {"transcript": "summary", "memory": "summary", "text": "text", "judge": "confidence"}[
        service
    ]
    return json.dumps({**payload, field: " " if service != "judge" else "0.8"})


@pytest.mark.asyncio
@pytest.mark.parametrize("service", PAYLOADS)
@pytest.mark.parametrize("defect", ["truncated", "fenced", "missing", "extra", "invalid_value"])
@pytest.mark.parametrize("corrected", [True, False])
async def test_services_require_model_correction(service, defect, corrected):
    attempts = 0

    def respond(messages, info):
        nonlocal attempts
        attempts += 1
        assert info.output_tools, "The schema must be sent to the model"
        if attempts > 1:
            assert any(
                isinstance(part, RetryPromptPart) for message in messages for part in message.parts
            ), "The model must receive validation feedback before retrying"
        arguments = (
            json.dumps(PAYLOADS[service])
            if corrected and attempts > 1
            else invalid_payload(service, defect)
        )
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, arguments)])

    with (
        patch("app.services.ai.transcript_analysis._get_client", return_value=object()),
        patch("app.services.ai.openai_credentials.create_openai_client", return_value=object()),
        patch("app.services.ai.call_judge.create_openai_client", return_value=object()),
        patch("app.services.ai.structured_output.OpenAIProvider", return_value=object()),
        patch(
            "app.services.ai.structured_output.OpenAIChatModel", return_value=FunctionModel(respond)
        ),
    ):
        if corrected:
            result = await run_service(service)
            assert attempts == 2
            if service == "transcript":
                assert result == PAYLOADS[service]
            elif service == "memory":
                assert result == PAYLOADS[service]["summary"]
            elif service == "text":
                assert result == PAYLOADS[service]["text"]
            else:
                assert result["confidence"] == 0.8
                assert result["scores"]["opening"]["quote"] == "Please call tomorrow."
        else:
            with pytest.raises(UnexpectedModelBehavior):
                await run_service(service)
            assert attempts == 3, "Initial attempt plus two corrections, with no fallback"
