"""Call transcript sentiment and intent extraction.

Uses OpenAI's JSON mode to pull structured signals (sentiment, intents,
topics, summary, objections, next steps) out of a voice call transcript.
"""

import json
from typing import Any

import structlog
from openai import AsyncOpenAI

from app.core.config import settings

logger = structlog.get_logger()

_MODEL = "gpt-4o-mini"

_SYSTEM_PROMPT = (
    "You are a sales call analyst. Analyze sales call transcripts and "
    "return structured JSON with sentiment, intents, topics, a short "
    "summary, objections, and next steps. Always return valid JSON."
)

_USER_PROMPT = (
    "Analyze this sales call transcript. Extract the caller's sentiment, "
    "primary intents, topics discussed, a 1-2 sentence summary, any "
    "objections raised, and proposed next steps.\n\n"
    "Return a JSON object with exactly these fields:\n"
    '- "sentiment": one of "positive", "neutral", "negative"\n'
    '- "sentiment_score": number between -1.0 and 1.0\n'
    '- "intents": array of short intent strings\n'
    '- "topics": array of short topic strings\n'
    '- "summary": 1-2 sentence string\n'
    '- "objections": array of short objection strings\n'
    '- "next_steps": array of short next-step strings\n\n'
    "TRANSCRIPT:\n{transcript}"
)

_ALLOWED_SENTIMENTS = {"positive", "neutral", "negative"}

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    sentiment = str(raw.get("sentiment", "neutral")).lower()
    if sentiment not in _ALLOWED_SENTIMENTS:
        sentiment = "neutral"

    try:
        score = float(raw.get("sentiment_score", 0.0))
    except (TypeError, ValueError):
        score = 0.0
    score = max(-1.0, min(1.0, score))

    def _str_list(key: str) -> list[str]:
        value = raw.get(key, [])
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if item]

    return {
        "sentiment": sentiment,
        "sentiment_score": score,
        "intents": _str_list("intents"),
        "topics": _str_list("topics"),
        "summary": str(raw.get("summary", "")),
        "objections": _str_list("objections"),
        "next_steps": _str_list("next_steps"),
    }


async def analyze_transcript(transcript: str) -> dict[str, Any]:
    """Analyze a call transcript and return structured signals.

    Args:
        transcript: Raw call transcript text.

    Returns:
        Dict with sentiment, sentiment_score, intents, topics, summary,
        objections and next_steps fields.
    """
    client = _get_client()

    response = await client.chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _USER_PROMPT.format(transcript=transcript)},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )

    text = response.choices[0].message.content or "{}"
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        logger.exception("transcript_analysis_json_decode_failed")
        raw = {}

    if not isinstance(raw, dict):
        raw = {}

    return _normalize(raw)
