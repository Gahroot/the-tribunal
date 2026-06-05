"""Rehearsal report scorer.

Turns a completed rehearsal transcript into a scored report: objection coverage,
whether the agent attempted a booking, tone, an overall grade, and concrete
strengths / gaps / prompt-or-knowledge improvement suggestions.

Reuses :func:`app.services.ai.transcript_analysis.analyze_transcript` to enrich
the report with sentiment/intent signals from the existing pipeline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import structlog
from openai import AsyncOpenAI

from app.services.ai.transcript_analysis import analyze_transcript

logger = structlog.get_logger()

_MODEL = "gpt-4o-mini"
_TIMEOUT_SECONDS = 45.0

_SYSTEM_PROMPT = (
    "You are a sales-enablement coach grading a rehearsal between a sales rep "
    "and a synthetic prospect. Grade ONLY the rep's performance, fairly and "
    "specifically. Always return valid JSON."
)


@dataclass(slots=True)
class RehearsalReport:
    """Structured rehearsal score + qualitative feedback."""

    overall_score: float
    objection_coverage: float
    booking_attempted: bool
    tone_score: float
    summary: str
    strengths: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    scores: dict[str, Any] = field(default_factory=dict)


def _format_transcript(transcript: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for turn in transcript:
        speaker = "PROSPECT" if turn.get("role") == "prospect" else "REP"
        lines.append(f"{speaker}: {turn.get('content', '')}")
    return "\n".join(lines)


def _clamp_score(value: Any, default: float = 0.0) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(100.0, score))


def _str_list(value: Any, limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item][:limit]


def _build_user_prompt(
    transcript_text: str,
    persona_name: str,
    objections: list[str],
    goal: str | None,
) -> str:
    objections_block = (
        "\n".join(f"- {o}" for o in objections) if objections else "- (none specified)"
    )
    goal_block = goal or "(not specified)"
    return (
        f"PROSPECT PERSONA: {persona_name}\n"
        f"PROSPECT'S WIN CONDITION: {goal_block}\n\n"
        "OBJECTIONS THE PROSPECT WAS EXPECTED TO RAISE:\n"
        f"{objections_block}\n\n"
        "TRANSCRIPT:\n"
        f"{transcript_text}\n\n"
        "Grade the REP. Return a JSON object with EXACTLY these fields:\n"
        '- "overall_score": number 0-100 (overall rehearsal quality)\n'
        '- "objection_coverage_score": number 0-100 (how well the rep '
        "addressed the expected objections that actually came up)\n"
        '- "objection_breakdown": array of objects '
        '{"objection": string, "addressed": boolean, "note": string}\n'
        '- "booking_attempted": boolean (did the rep try to book a meeting/'
        "appointment or propose a concrete next step time?)\n"
        '- "tone_score": number 0-100 (professional, empathetic, on-brand)\n'
        '- "tone_label": one of "warm", "neutral", "pushy", "robotic"\n'
        '- "summary": 1-2 sentence string\n'
        '- "strengths": array of short strings (what the rep did well)\n'
        '- "gaps": array of short strings (what the rep missed or did poorly)\n'
        '- "suggestions": array of short strings with concrete improvements to '
        "the rep's PROMPT or KNOWLEDGE BASE that would raise the score\n"
    )


async def score_rehearsal(
    *,
    client: AsyncOpenAI,
    transcript: list[dict[str, Any]],
    persona_name: str,
    objections: list[str],
    goal: str | None,
) -> RehearsalReport:
    """Score a rehearsal transcript into a structured report.

    Falls back to a low-signal but valid report if the LLM response can't be
    parsed, so a rehearsal always yields a result rather than failing hard.
    """
    transcript_text = _format_transcript(transcript)

    # Enrich with the existing transcript-analysis pipeline (sentiment/intents).
    analysis: dict[str, Any] = {}
    try:
        analysis = await analyze_transcript(transcript_text)
    except Exception:
        logger.exception("rehearsal_transcript_analysis_failed")

    raw: dict[str, Any] = {}
    try:
        response = await client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _build_user_prompt(transcript_text, persona_name, objections, goal),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        text = response.choices[0].message.content or "{}"
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            raw = parsed
    except json.JSONDecodeError:
        logger.exception("rehearsal_score_json_decode_failed")
    except Exception:
        logger.exception("rehearsal_score_failed")

    overall = _clamp_score(raw.get("overall_score"), default=0.0)
    objection_coverage = _clamp_score(raw.get("objection_coverage_score"), default=0.0)
    tone = _clamp_score(raw.get("tone_score"), default=0.0)
    booking_attempted = bool(raw.get("booking_attempted", False))

    breakdown = raw.get("objection_breakdown")
    objection_breakdown: list[dict[str, Any]] = []
    if isinstance(breakdown, list):
        for item in breakdown:
            if isinstance(item, dict):
                objection_breakdown.append(
                    {
                        "objection": str(item.get("objection", "")),
                        "addressed": bool(item.get("addressed", False)),
                        "note": str(item.get("note", "")),
                    }
                )

    scores = {
        "overall_score": overall,
        "objection_coverage_score": objection_coverage,
        "tone_score": tone,
        "tone_label": str(raw.get("tone_label", "neutral")),
        "booking_attempted": booking_attempted,
        "objection_breakdown": objection_breakdown,
        "sentiment": analysis.get("sentiment"),
        "sentiment_score": analysis.get("sentiment_score"),
        "intents": analysis.get("intents", []),
        "topics": analysis.get("topics", []),
    }

    return RehearsalReport(
        overall_score=overall,
        objection_coverage=objection_coverage,
        booking_attempted=booking_attempted,
        tone_score=tone,
        summary=str(raw.get("summary", "")) or analysis.get("summary", ""),
        strengths=_str_list(raw.get("strengths")),
        gaps=_str_list(raw.get("gaps")),
        suggestions=_str_list(raw.get("suggestions")),
        scores=scores,
    )
