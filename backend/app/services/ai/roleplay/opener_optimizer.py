"""First-touch opener optimizer.

Discovers the best *first-touch* opening message for outbound iMessage sales by
simulating each candidate opener against the synthetic prospect persona panel at
scale, then ranking openers by **downstream outcome** — did the prospect reply,
become engaged, and ultimately agree to buy / book — rather than tone alone.

This reuses the practice-arena engine so a rehearsal here behaves like the live
text pipeline:

- :func:`app.services.ai.roleplay.agent_responder.build_agent_system_prompt` and
  :func:`~app.services.ai.roleplay.agent_responder.generate_agent_reply` run the
  agent's *real* production prompt for follow-up turns.
- :func:`app.services.ai.roleplay.prospect_simulator.generate_prospect_reply`
  role-plays a believable prestyj-ICP prospect (``gpt-5.4-nano``).

The key difference from a normal rehearsal is direction: here the **agent opens**
with a candidate first-touch line and the prospect *reacts*, which is exactly the
outbound first-touch motion. A dedicated outcome scorer then classifies how far
each conversation advanced through the funnel.

The result is a reproducible, persistable :class:`OpenerSimulationReport` whose
ranked winners can later be promoted to production.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

import structlog
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.services.ai.roleplay.agent_responder import generate_agent_reply
from app.services.ai.roleplay.prospect_simulator import generate_prospect_reply
from app.services.ai.structured_output import generate_structured

logger = structlog.get_logger()

# Scoring model: a cheap, deterministic-ish judge (matches the report scorer).
_SCORER_MODEL = "gpt-4o-mini"
_SCORER_TIMEOUT_SECONDS = 45.0


class OutcomeScore(BaseModel):
    stage: Literal["disengaged", "replied", "engaged", "agreed_to_buy"]
    reply_quality: float = Field(ge=0, le=100)
    buying_intent: float = Field(ge=0, le=100)
    opener_craft: float = Field(ge=0, le=100)
    reached_close: bool
    agreed_pack: str | None
    escalated: bool
    rationale: str = Field(min_length=1)


# Funnel stages, ordered worst -> best, with the point value each is worth.
# The opener is graded on how far down this funnel the conversation travelled.
STAGE_POINTS: dict[str, float] = {
    "disengaged": 0.0,  # ignored, hostile, or shut the conversation down
    "replied": 35.0,  # answered but stayed cold / non-committal
    "engaged": 70.0,  # asked real questions / showed genuine interest
    "agreed_to_buy": 100.0,  # accepted a pack / checkout link / booked next step
}
_STAGE_ORDER = list(STAGE_POINTS.keys())

# Composite opener score weighting. Downstream OUTCOME dominates; opener craft
# (how well the first line specifically earned the next reply) is a minor factor.
_W_STAGE = 0.55
_W_BUYING_INTENT = 0.25
_W_OPENER_CRAFT = 0.20

_SCORER_SYSTEM_PROMPT = (
    "You are a sales-operations analyst grading an OUTBOUND first-touch sales "
    "conversation. The REP sent the very first message cold; the PROSPECT had "
    "not asked to be contacted. Judge how far the conversation advanced through "
    "the buying funnel as a result of the rep's outreach. Be strict and "
    "outcome-focused, not charmed by tone. Always return valid JSON."
)


@dataclass(frozen=True, slots=True)
class OpenerCandidate:
    """A candidate first-touch opener under test.

    ``strategy`` labels the data-driven angle (e.g. ``observed_ads``,
    ``pain_point``) so the ranked report explains *why* a winner wins, not just
    which string scored best.
    """

    id: str
    text: str
    strategy: str | None = None


@dataclass(frozen=True, slots=True)
class PersonaSpec:
    """The minimal persona fields the optimizer needs to simulate + score."""

    slug: str
    name: str
    persona_prompt: str
    goal: str | None = None
    objections: tuple[str, ...] = ()


@dataclass(slots=True)
class ConversationOutcome:
    """One scored opener-vs-persona conversation."""

    opener_id: str
    persona_slug: str
    repeat: int
    stage: str
    stage_points: float
    reply_quality: float
    buying_intent: float
    opener_craft: float
    reached_close: bool
    agreed_pack: str | None
    escalated: bool
    opener_score: float
    rationale: str
    transcript: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class OpenerAggregate:
    """Aggregated performance of one opener across the whole persona panel."""

    candidate: OpenerCandidate
    conversations: int
    mean_score: float
    reply_rate: float
    engaged_rate: float
    agreed_rate: float
    mean_buying_intent: float
    mean_opener_craft: float
    per_persona_mean_score: dict[str, float]
    agreed_packs: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["candidate"] = asdict(self.candidate)
        return data


@dataclass(slots=True)
class OpenerSimulationReport:
    """Reproducible, persistable ranked report of opener performance."""

    config_fingerprint: str
    generator: str
    prospect_model: str
    scorer_model: str
    workspace_id: str
    agent_name: str
    created_at: str
    base_seed: int | None
    persona_slugs: list[str]
    conversations_per_persona: int
    max_turns: int
    total_conversations: int
    rankings: list[OpenerAggregate]
    conversations: list[ConversationOutcome] = field(default_factory=list)

    def to_dict(self, *, include_transcripts: bool = True) -> dict[str, Any]:
        rankings = [agg.to_dict() for agg in self.rankings]
        conversations: list[dict[str, Any]] = []
        for convo in self.conversations:
            row = asdict(convo)
            if not include_transcripts:
                row.pop("transcript", None)
            conversations.append(row)
        return {
            "config_fingerprint": self.config_fingerprint,
            "generator": self.generator,
            "prospect_model": self.prospect_model,
            "scorer_model": self.scorer_model,
            "workspace_id": self.workspace_id,
            "agent_name": self.agent_name,
            "created_at": self.created_at,
            "base_seed": self.base_seed,
            "persona_slugs": self.persona_slugs,
            "conversations_per_persona": self.conversations_per_persona,
            "max_turns": self.max_turns,
            "total_conversations": self.total_conversations,
            "rankings": rankings,
            "conversations": conversations,
        }


def _format_transcript(transcript: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for turn in transcript:
        speaker = "PROSPECT" if turn.get("role") == "prospect" else "REP"
        lines.append(f"{speaker}: {turn.get('content', '')}")
    return "\n".join(lines)


def _clamp(value: Any, default: float = 0.0) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(100.0, score))


def _seed_for(base_seed: int | None, *parts: object) -> int | None:
    """Derive a stable per-conversation/per-call seed from the run's base seed.

    Returns ``None`` when no base seed is configured (fully sampled run).
    """
    if base_seed is None:
        return None
    digest = hashlib.sha256(
        ("|".join([str(base_seed), *(str(p) for p in parts)])).encode()
    ).hexdigest()
    # OpenAI seeds are 64-bit-ish ints; keep it comfortably in range.
    return int(digest[:12], 16)


def config_fingerprint(
    *,
    openers: Sequence[OpenerCandidate],
    persona_slugs: Sequence[str],
    conversations_per_persona: int,
    max_turns: int,
    prospect_model: str,
    scorer_model: str,
    base_seed: int | None,
    agent_prompt: str,
) -> str:
    """Hash everything that determines the run so identical configs are linkable.

    ``agent_prompt`` should be the agent's *durable* configured prompt, not a
    runtime-assembled prompt containing a clock/timestamp, so the same config
    yields the same fingerprint across runs.
    """
    payload = {
        "openers": [(o.id, o.text) for o in openers],
        "personas": sorted(persona_slugs),
        "conversations_per_persona": conversations_per_persona,
        "max_turns": max_turns,
        "prospect_model": prospect_model,
        "scorer_model": scorer_model,
        "base_seed": base_seed,
        "agent_prompt": hashlib.sha256(agent_prompt.encode()).hexdigest(),
    }
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


async def _simulate_conversation(
    *,
    client: AsyncOpenAI,
    system_prompt: str,
    opener: OpenerCandidate,
    persona: PersonaSpec,
    repeat: int,
    max_turns: int,
    agent_temperature: float,
    base_seed: int | None,
) -> list[dict[str, Any]]:
    """Run one outbound first-touch conversation.

    The agent opens with the candidate opener, the prospect reacts, and the
    agent follows its real production prompt for the remaining turns. The
    transcript ends on a prospect turn so the final stance is captured.
    """
    transcript: list[dict[str, Any]] = [{"role": "agent", "content": opener.text}]
    for turn in range(max_turns):
        prospect_text = await generate_prospect_reply(
            client=client,
            persona_prompt=persona.persona_prompt,
            transcript=transcript,
            seed=_seed_for(base_seed, opener.id, persona.slug, repeat, "p", turn),
        )
        transcript.append({"role": "prospect", "content": prospect_text})
        if turn < max_turns - 1:
            agent_text = await generate_agent_reply(
                client=client,
                system_prompt=system_prompt,
                transcript=transcript,
                temperature=agent_temperature,
                seed=_seed_for(base_seed, opener.id, persona.slug, repeat, "a", turn),
            )
            transcript.append({"role": "agent", "content": agent_text})
    return transcript


def _build_scorer_prompt(persona: PersonaSpec, transcript_text: str) -> str:
    objections = (
        "\n".join(f"- {o}" for o in persona.objections)
        if persona.objections
        else "- (none specified)"
    )
    goal = persona.goal or "(not specified)"
    return (
        f"PROSPECT PERSONA: {persona.name}\n"
        f"PROSPECT'S PRIVATE WIN CONDITION: {goal}\n\n"
        "OBJECTIONS THE PROSPECT MAY RAISE:\n"
        f"{objections}\n\n"
        "TRANSCRIPT (REP sent the first message cold):\n"
        f"{transcript_text}\n\n"
        "Grade the OUTCOME this first-touch opener produced. Return a JSON object "
        "with EXACTLY these fields:\n"
        '- "stage": one of "disengaged" (ignored/hostile/shut down), "replied" '
        '(answered but cold/non-committal), "engaged" (asked real questions or '
        'showed genuine interest), "agreed_to_buy" (accepted a pack, accepted a '
        "Stripe checkout link, or committed to a concrete next step/booking)\n"
        '- "reply_quality": number 0-100 (how substantive/positive the prospect\'s '
        "engagement was)\n"
        '- "buying_intent": number 0-100 (how close the prospect got to purchasing)\n'
        '- "opener_craft": number 0-100 (how well the REP\'s FIRST message '
        "specifically earned the next reply — relevance, hook, non-spammy)\n"
        '- "reached_close": boolean (did the rep get an explicit agreement to buy '
        "or book?)\n"
        '- "agreed_pack": string or null (which pack the prospect agreed to, e.g. '
        '"100", "300", "500", "1000", else null)\n'
        '- "escalated": boolean (did the conversation correctly hand off to a '
        "human for add-ons beyond the batch, e.g. running ads/consulting?)\n"
        '- "rationale": one short sentence explaining the stage\n'
    )


async def _score_conversation(
    *,
    client: AsyncOpenAI,
    opener: OpenerCandidate,
    persona: PersonaSpec,
    repeat: int,
    transcript: list[dict[str, Any]],
    base_seed: int | None,
) -> ConversationOutcome:
    transcript_text = _format_transcript(transcript)
    score = await generate_structured(
        client=client,
        model=_SCORER_MODEL,
        schema=OutcomeScore,
        system_prompt=_SCORER_SYSTEM_PROMPT,
        user_prompt=_build_scorer_prompt(persona, transcript_text),
        temperature=0.1,
        timeout=_SCORER_TIMEOUT_SECONDS,
        seed=_seed_for(base_seed, opener.id, persona.slug, repeat, "score"),
    )
    return build_outcome(
        opener_id=opener.id,
        persona_slug=persona.slug,
        repeat=repeat,
        raw=score.model_dump(),
        transcript=transcript,
    )


def normalize_stage(stage: Any) -> str:
    """Coerce a stage label to a known funnel stage (defaults to ``disengaged``)."""
    value = str(stage or "").strip().lower()
    return value if value in STAGE_POINTS else "disengaged"


def compute_opener_score(stage_points: float, buying_intent: float, opener_craft: float) -> float:
    """The single, canonical opener-score formula (outcome-weighted)."""
    return round(
        _W_STAGE * stage_points + _W_BUYING_INTENT * buying_intent + _W_OPENER_CRAFT * opener_craft,
        2,
    )


def build_outcome(
    *,
    opener_id: str,
    persona_slug: str,
    repeat: int,
    raw: dict[str, Any],
    transcript: list[dict[str, Any]] | None = None,
) -> ConversationOutcome:
    """Build a scored :class:`ConversationOutcome` from raw judged fields.

    Shared by the live OpenAI scorer and the offline (agent-driven) ingestion
    path so the opener-score formula and stage normalization are identical no
    matter who generated and judged the conversation.
    """
    stage = normalize_stage(raw.get("stage"))
    stage_points = STAGE_POINTS[stage]
    reply_quality = _clamp(raw.get("reply_quality"))
    buying_intent = _clamp(raw.get("buying_intent"))
    opener_craft = _clamp(raw.get("opener_craft"))
    reached_close = bool(raw.get("reached_close", False)) or stage == "agreed_to_buy"
    agreed_pack_raw = raw.get("agreed_pack")
    agreed_pack = str(agreed_pack_raw) if agreed_pack_raw not in (None, "", "null") else None
    escalated = bool(raw.get("escalated", False))

    return ConversationOutcome(
        opener_id=opener_id,
        persona_slug=persona_slug,
        repeat=repeat,
        stage=stage,
        stage_points=stage_points,
        reply_quality=reply_quality,
        buying_intent=buying_intent,
        opener_craft=opener_craft,
        reached_close=reached_close,
        agreed_pack=agreed_pack,
        escalated=escalated,
        opener_score=compute_opener_score(stage_points, buying_intent, opener_craft),
        rationale=str(raw.get("rationale", "")),
        transcript=list(transcript or []),
    )


async def _run_one(
    *,
    client: AsyncOpenAI,
    system_prompt: str,
    opener: OpenerCandidate,
    persona: PersonaSpec,
    repeat: int,
    max_turns: int,
    agent_temperature: float,
    base_seed: int | None,
    semaphore: asyncio.Semaphore,
) -> ConversationOutcome:
    async with semaphore:
        transcript = await _simulate_conversation(
            client=client,
            system_prompt=system_prompt,
            opener=opener,
            persona=persona,
            repeat=repeat,
            max_turns=max_turns,
            agent_temperature=agent_temperature,
            base_seed=base_seed,
        )
        return await _score_conversation(
            client=client,
            opener=opener,
            persona=persona,
            repeat=repeat,
            transcript=transcript,
            base_seed=base_seed,
        )


def _aggregate(
    opener: OpenerCandidate,
    outcomes: list[ConversationOutcome],
) -> OpenerAggregate:
    n = len(outcomes)
    if n == 0:
        return OpenerAggregate(
            candidate=opener,
            conversations=0,
            mean_score=0.0,
            reply_rate=0.0,
            engaged_rate=0.0,
            agreed_rate=0.0,
            mean_buying_intent=0.0,
            mean_opener_craft=0.0,
            per_persona_mean_score={},
            agreed_packs={},
        )

    def rate(predicate: Any) -> float:
        return round(sum(1 for o in outcomes if predicate(o)) / n, 4)

    replied_idx = _STAGE_ORDER.index("replied")
    engaged_idx = _STAGE_ORDER.index("engaged")

    per_persona: dict[str, list[float]] = {}
    for o in outcomes:
        per_persona.setdefault(o.persona_slug, []).append(o.opener_score)
    per_persona_mean = {
        slug: round(sum(scores) / len(scores), 2) for slug, scores in per_persona.items()
    }

    agreed_packs: dict[str, int] = {}
    for o in outcomes:
        if o.agreed_pack:
            agreed_packs[o.agreed_pack] = agreed_packs.get(o.agreed_pack, 0) + 1

    return OpenerAggregate(
        candidate=opener,
        conversations=n,
        mean_score=round(sum(o.opener_score for o in outcomes) / n, 2),
        reply_rate=rate(lambda o: _STAGE_ORDER.index(o.stage) >= replied_idx),
        engaged_rate=rate(lambda o: _STAGE_ORDER.index(o.stage) >= engaged_idx),
        agreed_rate=rate(lambda o: o.stage == "agreed_to_buy" or o.reached_close),
        mean_buying_intent=round(sum(o.buying_intent for o in outcomes) / n, 2),
        mean_opener_craft=round(sum(o.opener_craft for o in outcomes) / n, 2),
        per_persona_mean_score=per_persona_mean,
        agreed_packs=agreed_packs,
    )


async def run_opener_simulation(
    *,
    client: AsyncOpenAI,
    workspace_id: str,
    agent_name: str,
    agent_system_prompt: str,
    agent_temperature: float,
    openers: Sequence[OpenerCandidate],
    personas: Sequence[PersonaSpec],
    conversations_per_persona: int = 3,
    max_turns: int = 4,
    concurrency: int = 6,
    base_seed: int | None = None,
    prospect_model: str = "gpt-5.4-nano",
    prompt_identity: str | None = None,
) -> OpenerSimulationReport:
    """Simulate every opener across the persona panel and rank by outcome.

    Runs ``openers x personas x conversations_per_persona`` first-touch
    conversations concurrently (bounded by ``concurrency``), scores each by how
    far it advanced through the funnel, aggregates per opener, and returns a
    ranked, reproducible report.
    """
    if not openers:
        raise ValueError("At least one candidate opener is required")
    if not personas:
        raise ValueError("At least one persona is required")

    semaphore = asyncio.Semaphore(max(1, concurrency))
    tasks: list[asyncio.Task[ConversationOutcome]] = []
    for opener in openers:
        for persona in personas:
            for repeat in range(conversations_per_persona):
                tasks.append(
                    asyncio.ensure_future(
                        _run_one(
                            client=client,
                            system_prompt=agent_system_prompt,
                            opener=opener,
                            persona=persona,
                            repeat=repeat,
                            max_turns=max_turns,
                            agent_temperature=agent_temperature,
                            base_seed=base_seed,
                            semaphore=semaphore,
                        )
                    )
                )

    outcomes: list[ConversationOutcome] = list(await asyncio.gather(*tasks))

    return _assemble_report(
        outcomes=outcomes,
        openers=openers,
        persona_slugs=[p.slug for p in personas],
        workspace_id=workspace_id,
        agent_name=agent_name,
        agent_system_prompt=agent_system_prompt,
        prompt_identity=prompt_identity,
        conversations_per_persona=conversations_per_persona,
        max_turns=max_turns,
        base_seed=base_seed,
        generator="openai",
        prospect_model=prospect_model,
        scorer_model=_SCORER_MODEL,
    )


def _assemble_report(
    *,
    outcomes: list[ConversationOutcome],
    openers: Sequence[OpenerCandidate],
    persona_slugs: Sequence[str],
    workspace_id: str,
    agent_name: str,
    agent_system_prompt: str,
    prompt_identity: str | None,
    conversations_per_persona: int,
    max_turns: int,
    base_seed: int | None,
    generator: str,
    prospect_model: str,
    scorer_model: str,
) -> OpenerSimulationReport:
    """Aggregate, rank, fingerprint, and package scored outcomes into a report.

    The single ranking/persistence path shared by the live OpenAI simulation and
    the offline (agent-driven) ingestion path, so both produce identical report
    shapes and identical fingerprints for identical configs.
    """
    by_opener: dict[str, list[ConversationOutcome]] = {o.id: [] for o in openers}
    for outcome in outcomes:
        if outcome.opener_id in by_opener:
            by_opener[outcome.opener_id].append(outcome)

    aggregates = [_aggregate(opener, by_opener[opener.id]) for opener in openers]
    # Rank by mean outcome score, then agreed-rate, then engaged-rate as tie-breaks.
    aggregates.sort(
        key=lambda a: (a.mean_score, a.agreed_rate, a.engaged_rate),
        reverse=True,
    )

    # Stable, deterministic conversation ordering for reproducible artifacts.
    ordered = sorted(outcomes, key=lambda o: (o.opener_id, o.persona_slug, o.repeat))

    fingerprint = config_fingerprint(
        openers=openers,
        persona_slugs=persona_slugs,
        conversations_per_persona=conversations_per_persona,
        max_turns=max_turns,
        prospect_model=prospect_model,
        scorer_model=scorer_model,
        base_seed=base_seed,
        agent_prompt=prompt_identity or agent_system_prompt,
    )

    return OpenerSimulationReport(
        config_fingerprint=fingerprint,
        generator=generator,
        prospect_model=prospect_model,
        scorer_model=scorer_model,
        workspace_id=workspace_id,
        agent_name=agent_name,
        created_at=datetime.now(UTC).isoformat(),
        base_seed=base_seed,
        persona_slugs=list(persona_slugs),
        conversations_per_persona=conversations_per_persona,
        max_turns=max_turns,
        total_conversations=len(ordered),
        rankings=aggregates,
        conversations=ordered,
    )


def build_report_from_outcomes(
    *,
    rows: Sequence[dict[str, Any]],
    openers: Sequence[OpenerCandidate],
    persona_slugs: Sequence[str],
    workspace_id: str,
    agent_name: str,
    agent_system_prompt: str,
    conversations_per_persona: int,
    max_turns: int,
    base_seed: int | None = None,
    generator: str = "agent",
    prospect_model: str = "agent",
    scorer_model: str = "agent",
    prompt_identity: str | None = None,
) -> OpenerSimulationReport:
    """Build a ranked report from externally-judged conversation rows.

    This is the offline path used when the conversations and outcome judgments are
    produced *without* the OpenAI client (e.g. the orchestrating agent role-plays
    the personas and scores the funnel stage itself). Each row carries
    ``opener_id``, ``persona_slug``, ``repeat`` and the judged fields consumed by
    :func:`build_outcome` (``stage``, ``buying_intent``, ``opener_craft``, ...).
    Scoring, aggregation, ranking, and fingerprinting stay in this module so the
    output is identical in shape and reproducibility to the live path.
    """
    valid_openers = {o.id for o in openers}
    valid_personas = set(persona_slugs)
    outcomes: list[ConversationOutcome] = []
    for row in rows:
        opener_id = str(row.get("opener_id", ""))
        persona_slug = str(row.get("persona_slug", ""))
        if opener_id not in valid_openers:
            raise ValueError(f"unknown opener_id in outcome row: {opener_id!r}")
        if persona_slug not in valid_personas:
            raise ValueError(f"unknown persona_slug in outcome row: {persona_slug!r}")
        transcript = row.get("transcript")
        outcomes.append(
            build_outcome(
                opener_id=opener_id,
                persona_slug=persona_slug,
                repeat=int(row.get("repeat", 0)),
                raw=row,
                transcript=transcript if isinstance(transcript, list) else None,
            )
        )

    return _assemble_report(
        outcomes=outcomes,
        openers=openers,
        persona_slugs=persona_slugs,
        workspace_id=workspace_id,
        agent_name=agent_name,
        agent_system_prompt=agent_system_prompt,
        prompt_identity=prompt_identity,
        conversations_per_persona=conversations_per_persona,
        max_turns=max_turns,
        base_seed=base_seed,
        generator=generator,
        prospect_model=prospect_model,
        scorer_model=scorer_model,
    )
