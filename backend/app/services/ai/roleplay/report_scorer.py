"""Rehearsal report scorer.

Turns a completed rehearsal transcript into a scored report: objection coverage,
whether the agent attempted a booking, tone, an overall grade, and concrete
strengths / gaps / prompt-or-knowledge improvement suggestions.

Reuses :func:`app.services.ai.transcript_analysis.analyze_transcript` to enrich
the report with sentiment/intent signals from the existing pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.services.ai.structured_output import generate_structured
from app.services.ai.transcript_analysis import analyze_transcript

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


class ObjectionResult(BaseModel):
    objection: str
    addressed: bool
    note: str


class RehearsalScore(BaseModel):
    overall_score: float = Field(ge=0, le=100)
    objection_coverage_score: float = Field(ge=0, le=100)
    tone_score: float = Field(ge=0, le=100)
    booking_attempted: bool
    tone_label: Literal["warm", "neutral", "pushy", "robotic"]
    objection_breakdown: list[ObjectionResult]
    summary: str = Field(min_length=1)
    strengths: list[str]
    gaps: list[str]
    suggestions: list[str]


def _format_transcript(transcript: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for turn in transcript:
        speaker = "PROSPECT" if turn.get("role") == "prospect" else "REP"
        lines.append(f"{speaker}: {turn.get('content', '')}")
    return "\n".join(lines)


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

    Invalid scores are retried with the model, then fail rather than being
    recorded as a successful low-signal rehearsal.
    """
    transcript_text = _format_transcript(transcript)

    # Enrich with the existing transcript-analysis pipeline (sentiment/intents).
    analysis = await analyze_transcript(transcript_text)
    raw = await generate_structured(
        client=client,
        model=_MODEL,
        schema=RehearsalScore,
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=_build_user_prompt(transcript_text, persona_name, objections, goal),
        temperature=0.2,
        timeout=_TIMEOUT_SECONDS,
    )

    scores = {
        "overall_score": raw.overall_score,
        "objection_coverage_score": raw.objection_coverage_score,
        "tone_score": raw.tone_score,
        "tone_label": raw.tone_label,
        "booking_attempted": raw.booking_attempted,
        "objection_breakdown": [item.model_dump() for item in raw.objection_breakdown],
        "sentiment": analysis.get("sentiment"),
        "sentiment_score": analysis.get("sentiment_score"),
        "intents": analysis.get("intents", []),
        "topics": analysis.get("topics", []),
    }

    return RehearsalReport(
        overall_score=raw.overall_score,
        objection_coverage=raw.objection_coverage_score,
        booking_attempted=raw.booking_attempted,
        tone_score=raw.tone_score,
        summary=raw.summary,
        strengths=raw.strengths[:8],
        gaps=raw.gaps[:8],
        suggestions=raw.suggestions[:8],
        scores=scores,
    )
