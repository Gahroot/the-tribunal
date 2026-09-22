"""Discover the best first-touch opener for Prestyj Batch Video Ads by simulation.

Ranks candidate first-touch openers by **downstream outcome** (reply -> engaged
-> agreed-to-buy / booked), not tone, by simulating each opener against the
prestyj synthetic-prospect persona panel for many conversations.

The candidate openers are chosen by DATA: by default they are synthesized from
the seeded ad-library advertiser signals in the target workspace (how long their
ads have been running, creative-refresh rate, recommended pack, pain points), so
the starting messages are grounded in real lead data and the *ranking* is decided
by simulation rather than a guess. Pass ``--openers-file`` to test your own set.

Who runs the simulation is pluggable:

* ``--generator agent`` (default) — the orchestrating agent IS the simulation
  engine. The harness emits a deterministic conversation PLAN (every opener x
  persona x repeat, with the agent's real system prompt and each persona's
  in-character prompt). The agent role-plays the prospects, judges each
  conversation's funnel stage, and writes an outcomes file; the harness ingests
  it and produces the ranked, persisted report. No external LLM is involved.
* ``--generator openai`` — optional: drive the conversations with the live
  practice-arena engine (``gpt-5.4-nano`` prospects) when an OpenAI credential is
  configured for the workspace.

Output is reproducible (a config fingerprint + optional ``--seed``) and persisted
to a JSON artifact so winning openers can later be promoted to production.

Run from ``backend/`` against the seeded Prestyj workspace:

    # 1. Emit the conversation plan for the agent to role-play.
    uv run python scripts/dev/optimize_openers.py --env local --emit-plan out/plan.json

    # 2. (agent fills out/outcomes.json) Rank the agent-judged outcomes.
    uv run python scripts/dev/optimize_openers.py --env local --outcomes-file out/outcomes.json

    # Optional: drive it with the live OpenAI engine instead.
    uv run python scripts/dev/optimize_openers.py --env local --generator openai
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import statistics
from pathlib import Path
from typing import Any

from scripts._harness import (
    EXIT_FAILURE,
    EXIT_OK,
    EXIT_USAGE,
    ExecutionContext,
    bootstrap,
    log_event,
    run,
)


def _configure(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("simulation")
    group.add_argument(
        "--workspace-slug",
        default="prestyj-batch-video-ads-demo",
        help="Slug of the seeded workspace to load the agent + personas from.",
    )
    group.add_argument(
        "--generator",
        choices=("agent", "openai"),
        default="agent",
        help="Who runs the prospects: the orchestrating agent (default) or live OpenAI.",
    )
    group.add_argument(
        "--conversations-per-persona",
        type=int,
        default=2,
        help="How many conversations to simulate per opener x persona.",
    )
    group.add_argument(
        "--max-turns",
        type=int,
        default=3,
        help="Prospect turns per conversation (the agent replies between them).",
    )
    group.add_argument(
        "--concurrency",
        type=int,
        default=6,
        help="Max conversations simulated in parallel (openai generator only).",
    )
    group.add_argument(
        "--seed",
        type=int,
        default=20260601,
        help="Base seed for reproducible sampling. Use 0 to disable seeding.",
    )
    group.add_argument(
        "--personas",
        choices=("prestyj", "all"),
        default="prestyj",
        help="Which persona panel to run against (prestyj-only by default).",
    )
    group.add_argument(
        "--openers-file",
        type=Path,
        default=None,
        help=(
            "Optional JSON file of candidate openers: a list of strings, or of "
            '{"id","text","strategy"} objects. Defaults to data-driven openers.'
        ),
    )
    group.add_argument(
        "--emit-plan",
        type=Path,
        default=None,
        help="Write the conversation plan (for the agent to role-play) to this path and exit.",
    )
    group.add_argument(
        "--outcomes-file",
        type=Path,
        default=None,
        help="Ingest agent-judged conversation outcomes from this JSON and rank them.",
    )
    group.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Where to persist the ranked JSON report (defaults under scripts/out/).",
    )
    group.add_argument(
        "--top",
        type=int,
        default=10,
        help="How many ranked openers to print.",
    )
    group.add_argument(
        "--no-transcripts",
        action="store_true",
        help="Exclude per-conversation transcripts from the persisted artifact.",
    )


class _SetupError(Exception):
    """Raised when the workspace/agent/personas/openers cannot be loaded."""


class _Setup:
    """Loaded simulation inputs shared by every generator/plan path."""

    def __init__(
        self,
        *,
        workspace_id: str,
        agent_name: str,
        agent_temperature: float,
        system_prompt: str,
        prompt_identity: str,
        personas: list[Any],
        openers: list[Any],
        opener_source: str,
    ) -> None:
        self.workspace_id = workspace_id
        self.agent_name = agent_name
        self.agent_temperature = agent_temperature
        self.system_prompt = system_prompt
        self.prompt_identity = prompt_identity
        self.personas = personas
        self.openers = openers
        self.opener_source = opener_source


async def _load_setup(args: argparse.Namespace) -> _Setup:
    """Resolve workspace, agent, persona panel, openers, and system prompt."""
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.agent import Agent
    from app.models.contact import Contact
    from app.models.workspace import Workspace
    from app.services.ai.message_context_builder import get_workspace_timezone
    from app.services.ai.roleplay.agent_responder import build_agent_system_prompt
    from app.services.ai.roleplay.opener_optimizer import PersonaSpec
    from app.services.ai.roleplay.roleplay_service import RoleplayService

    async with AsyncSessionLocal() as db:
        workspace = (
            await db.execute(select(Workspace).where(Workspace.slug == args.workspace_slug))
        ).scalar_one_or_none()
        if workspace is None:
            raise _SetupError(
                f"workspace {args.workspace_slug!r} not found — seed it first "
                "(uv run python -m scripts.demo.seed_prestyj)"
            )

        # The seeded autonomous closer is this workspace's text agent.
        agent = (
            (
                await db.execute(
                    select(Agent)
                    .where(Agent.workspace_id == workspace.id, Agent.is_active.is_(True))
                    .order_by(Agent.created_at.asc())
                )
            )
            .scalars()
            .first()
        )
        if agent is None:
            raise _SetupError("no active agent in workspace")

        # Persona panel from the prestyj persona library.
        service = RoleplayService(db)
        all_personas = await service.list_personas(workspace.id)
        if args.personas == "prestyj":
            panel = [p for p in all_personas if p.slug.startswith("prestyj-")]
        else:
            panel = list(all_personas)
        if not panel:
            raise _SetupError(f"no personas available for filter {args.personas!r}")
        personas = [
            PersonaSpec(
                slug=p.slug,
                name=p.name,
                persona_prompt=p.persona_prompt,
                goal=p.goal,
                objections=tuple(p.objections or ()),
            )
            for p in panel
        ]

        # Candidate openers: data-driven from seeded leads, or operator-supplied.
        if args.openers_file is not None:
            openers = _load_openers_file(args.openers_file)
            opener_source = str(args.openers_file)
        else:
            contacts = (
                (
                    await db.execute(
                        select(Contact).where(
                            Contact.workspace_id == workspace.id,
                            Contact.source == "ad_library",
                        )
                    )
                )
                .scalars()
                .all()
            )
            openers = _data_driven_openers(list(contacts))
            opener_source = f"data-driven from {len(contacts)} ad-library leads"
        if not openers:
            raise _SetupError("no candidate openers")

        timezone = await get_workspace_timezone(workspace.id, db)
        system_prompt = await build_agent_system_prompt(db, agent, timezone=timezone)
        return _Setup(
            workspace_id=str(workspace.id),
            agent_name=agent.name,
            agent_temperature=float(agent.temperature or 0.7),
            system_prompt=system_prompt,
            prompt_identity=agent.system_prompt or "",
            personas=personas,
            openers=openers,
            opener_source=opener_source,
        )


async def _amain(ctx: ExecutionContext, args: argparse.Namespace) -> int:
    from app.services.ai.roleplay.opener_optimizer import build_report_from_outcomes

    base_seed = args.seed or None
    logger = ctx.logger

    try:
        setup = await _load_setup(args)
    except _SetupError as exc:
        log_event(logger, logging.ERROR, str(exc), slug=args.workspace_slug)
        return EXIT_FAILURE

    workspace_id = setup.workspace_id
    agent_name = setup.agent_name
    agent_temperature = setup.agent_temperature
    system_prompt = setup.system_prompt
    prompt_identity = setup.prompt_identity
    personas = setup.personas
    openers = setup.openers
    opener_source = setup.opener_source

    # ── Plan emission: hand the agent the matrix to role-play ────────────────
    if args.emit_plan is not None:
        return _emit_plan(
            args=args,
            openers=openers,
            personas=personas,
            workspace_id=workspace_id,
            agent_name=agent_name,
            system_prompt=system_prompt,
            opener_source=opener_source,
            base_seed=base_seed,
            logger=logger,
        )

    # ── Ingestion: rank agent-judged outcomes ────────────────────────────────
    if args.generator == "agent":
        if args.outcomes_file is None:
            log_event(
                logger,
                logging.ERROR,
                "agent generator needs --emit-plan (to produce the plan) then "
                "--outcomes-file (the judged conversations to rank)",
            )
            return EXIT_USAGE
        rows = _load_outcomes_file(args.outcomes_file)
        report = build_report_from_outcomes(
            rows=rows,
            openers=openers,
            persona_slugs=[p.slug for p in personas],
            workspace_id=workspace_id,
            agent_name=agent_name,
            agent_system_prompt=system_prompt,
            conversations_per_persona=args.conversations_per_persona,
            max_turns=args.max_turns,
            base_seed=base_seed,
            generator="agent",
            prompt_identity=prompt_identity,
        )
    else:
        report = await _run_openai_generator(
            args=args,
            openers=openers,
            personas=personas,
            workspace_id=workspace_id,
            agent_name=agent_name,
            agent_temperature=agent_temperature,
            system_prompt=system_prompt,
            prompt_identity=prompt_identity,
            opener_source=opener_source,
            base_seed=base_seed,
            logger=logger,
        )
        if report is None:
            return EXIT_FAILURE

    output_path = _persist_report(report, args)
    _print_report(report, top=args.top, output_path=output_path)
    return EXIT_OK


def _emit_plan(
    *,
    args: argparse.Namespace,
    openers: list[Any],
    personas: list[Any],
    workspace_id: str,
    agent_name: str,
    system_prompt: str,
    opener_source: str,
    base_seed: int | None,
    logger: logging.Logger,
) -> int:
    """Write the deterministic conversation plan for the agent to role-play."""
    conversations: list[dict[str, Any]] = []
    for opener in openers:
        for persona in personas:
            for repeat in range(args.conversations_per_persona):
                conversations.append(
                    {
                        "opener_id": opener.id,
                        "persona_slug": persona.slug,
                        "repeat": repeat,
                        "opener_text": opener.text,
                    }
                )

    plan = {
        "instructions": (
            "Role-play each conversation as the prospect persona reacting to the "
            "REP's opener (an OUTBOUND first-touch; the prospect did NOT ask to be "
            "contacted). The REP follows the agent system prompt. For each entry, "
            "judge the OUTCOME and append a row to an outcomes file with: opener_id, "
            "persona_slug, repeat, stage (disengaged|replied|engaged|agreed_to_buy), "
            "buying_intent (0-100), opener_craft (0-100), reply_quality (0-100), "
            "reached_close (bool), agreed_pack (str|null), escalated (bool), "
            "rationale (str), and optionally transcript (list of {role,content})."
        ),
        "workspace_id": workspace_id,
        "agent_name": agent_name,
        "agent_system_prompt": system_prompt,
        "opener_source": opener_source,
        "base_seed": base_seed,
        "conversations_per_persona": args.conversations_per_persona,
        "max_turns": args.max_turns,
        "openers": [{"id": o.id, "strategy": o.strategy, "text": o.text} for o in openers],
        "personas": [
            {
                "slug": p.slug,
                "name": p.name,
                "goal": p.goal,
                "objections": list(p.objections),
                "persona_prompt": p.persona_prompt,
            }
            for p in personas
        ],
        "conversations": conversations,
    }

    args.emit_plan.parent.mkdir(parents=True, exist_ok=True)
    args.emit_plan.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    log_event(
        logger,
        logging.INFO,
        "emitted conversation plan for agent role-play",
        path=str(args.emit_plan),
        conversations=len(conversations),
        openers=len(openers),
        personas=len(personas),
    )
    print(
        f"\nPlan written to {args.emit_plan} "
        f"({len(conversations)} conversations across {len(openers)} openers "
        f"x {len(personas)} personas).\n"
        "Role-play + judge each conversation, write the outcomes JSON, then run "
        "with --outcomes-file <path> to produce the ranked report."
    )
    return EXIT_OK


async def _run_openai_generator(
    *,
    args: argparse.Namespace,
    openers: list[Any],
    personas: list[Any],
    workspace_id: str,
    agent_name: str,
    agent_temperature: float,
    system_prompt: str,
    prompt_identity: str,
    opener_source: str,
    base_seed: int | None,
    logger: logging.Logger,
) -> Any:
    """Optional live path: drive the conversations with the OpenAI engine."""
    import uuid

    from openai import AsyncOpenAI

    from app.db.session import AsyncSessionLocal
    from app.services.ai.openai_credentials import get_workspace_openai_bearer_token
    from app.services.ai.roleplay.opener_optimizer import run_opener_simulation

    async with AsyncSessionLocal() as db:
        token = await get_workspace_openai_bearer_token(db, uuid.UUID(workspace_id))
    if not token:
        log_event(logger, logging.ERROR, "no OpenAI credential resolvable for workspace")
        return None
    client = AsyncOpenAI(api_key=token)

    total = len(openers) * len(personas) * args.conversations_per_persona
    log_event(
        logger,
        logging.INFO,
        "running openai opener simulation",
        agent=agent_name,
        openers=len(openers),
        personas=len(personas),
        total_conversations=total,
        opener_source=opener_source,
        base_seed=base_seed,
    )
    return await run_opener_simulation(
        client=client,
        workspace_id=workspace_id,
        agent_name=agent_name,
        agent_system_prompt=system_prompt,
        agent_temperature=agent_temperature,
        prompt_identity=prompt_identity,
        openers=openers,
        personas=personas,
        conversations_per_persona=args.conversations_per_persona,
        max_turns=args.max_turns,
        concurrency=args.concurrency,
        base_seed=base_seed,
    )


def _persist_report(report: Any, args: argparse.Namespace) -> Path:
    """Write the reproducible ranked report to its JSON artifact path."""
    output_path = args.output or (
        Path(__file__).resolve().parents[1] / "out" / f"opener_sim_{report.config_fingerprint}.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.to_dict(include_transcripts=not args.no_transcripts), indent=2),
        encoding="utf-8",
    )
    return output_path


def _data_driven_openers(contacts: list[Any]) -> list[Any]:
    """Synthesize candidate openers grounded in seeded lead data.

    Computes aggregate signals across the ad-library leads (ad longevity,
    creative-refresh rate, dominant pack recommendation, pain themes) and bakes
    those real numbers into a panel of distinct opener strategies. The simulation
    then decides which strategy wins, so the *starting message is data-driven and
    the ranking is data-decided* rather than guessed.
    """
    from app.services.ai.roleplay.opener_optimizer import OpenerCandidate

    longest_runs: list[int] = []
    refresh_rates: list[float] = []
    anchor_votes = 0
    pain_terms: dict[str, int] = {}
    for c in contacts:
        intel = getattr(c, "business_intel", None) or {}
        observed = intel.get("observed_ads", {}) if isinstance(intel, dict) else {}
        if isinstance(observed, dict):
            if isinstance(observed.get("longest_running_days"), int | float):
                longest_runs.append(int(observed["longest_running_days"]))
            if isinstance(observed.get("creative_refresh_rate"), int | float):
                refresh_rates.append(float(observed["creative_refresh_rate"]))
        if isinstance(intel, dict) and intel.get("recommended_pack_key") == "anchor_500":
            anchor_votes += 1
        signals = getattr(c, "qualification_signals", None) or {}
        if isinstance(signals, dict):
            for pain in signals.get("pain_points", []) or []:
                for token in str(pain).lower().split():
                    if len(token) > 4:
                        pain_terms[token] = pain_terms.get(token, 0) + 1

    # Real numbers derived from the lead data.
    median_run = int(statistics.median(longest_runs)) if longest_runs else 120
    max_run = max(longest_runs) if longest_runs else median_run
    run_months = max(1, round(max_run / 30))
    median_refresh = round(statistics.median(refresh_rates), 2) if refresh_rates else 0.2
    anchor_share = round(anchor_votes / len(contacts), 2) if contacts else 0.0
    top_pain = max(pain_terms, key=lambda k: pain_terms[k]) if pain_terms else "creative"

    return [
        OpenerCandidate(
            id="observed_ads_longevity",
            strategy="observed_ads_longevity",
            text=(
                f"Hey — noticed your team's been running basically the same ad for "
                f"~{run_months} months now. That usually means the winners are getting "
                "tired. Want a faster way to test fresh hooks?"
            ),
        ),
        OpenerCandidate(
            id="creative_fatigue_pain",
            strategy="creative_fatigue_pain",
            text=(
                f"Quick one — is {top_pain} fatigue starting to drag your paid social "
                "numbers? We turn one short recording into a big batch of fresh ad "
                "variations so you always have new angles to test."
            ),
        ),
        OpenerCandidate(
            id="refresh_rate_gap",
            strategy="refresh_rate_gap",
            text=(
                f"Saw your ad creative refresh rate is sitting around {median_refresh}. "
                "Most accounts that low are leaving performance on the table. Mind if I "
                "share how we get brands testing way more hooks per month?"
            ),
        ),
        OpenerCandidate(
            id="volume_testing",
            strategy="volume_testing",
            text=(
                "What if you could test 100+ ad variations from a single 15-minute "
                "recording? We script, film via teleprompter, edit, and ship 9:16 files "
                "in 1-2 business days. Worth a look?"
            ),
        ),
        OpenerCandidate(
            id="cost_per_winner",
            strategy="cost_per_winner",
            text=(
                "Most brands obsess over cost per ad — the real metric is cost per "
                "winner. More tested variations = cheaper winners. Can I show you how we "
                "make that math work?"
            ),
        ),
        OpenerCandidate(
            id="direct_qualifier",
            strategy="direct_qualifier",
            text="Quick question — are you still running paid social ads for your business?",
        ),
        OpenerCandidate(
            id="speed_delivery",
            strategy="speed_delivery",
            text=(
                "If you recorded one short selfie-style video this week, we could hand you "
                "a batch of platform-ready ads in 1-2 business days. Want the details?"
            ),
        ),
        OpenerCandidate(
            id="anchor_volume_value",
            strategy="anchor_volume_value",
            text=(
                f"Most ad-running brands like yours land on our 500-ad pack — enough "
                f"volume to test hooks, angles, and CTAs without creative fatigue "
                f"({int(anchor_share * 100)}% of the accounts we look at fit it). Curious?"
            ),
        ),
    ]


def _load_openers_file(path: Path) -> list[Any]:
    from app.services.ai.roleplay.opener_optimizer import OpenerCandidate

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("openers file must contain a JSON list")
    openers: list[OpenerCandidate] = []
    for i, item in enumerate(raw):
        if isinstance(item, str):
            openers.append(OpenerCandidate(id=f"opener_{i + 1}", text=item))
        elif isinstance(item, dict) and item.get("text"):
            openers.append(
                OpenerCandidate(
                    id=str(item.get("id") or f"opener_{i + 1}"),
                    text=str(item["text"]),
                    strategy=item.get("strategy"),
                )
            )
        else:
            raise ValueError(f"invalid opener entry at index {i}")
    seen: set[str] = set()
    for o in openers:
        if o.id in seen:
            raise ValueError(f"duplicate opener id: {o.id}")
        seen.add(o.id)
    return openers


def _load_outcomes_file(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    # Accept either a bare list of rows or the plan-shaped {"conversations": [...]}.
    rows = (raw.get("outcomes") or raw.get("conversations")) if isinstance(raw, dict) else raw
    if not isinstance(rows, list) or not rows:
        raise ValueError("outcomes file must contain a non-empty list of judged rows")
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"outcome row {i} is not an object")
        if "opener_id" not in row or "persona_slug" not in row:
            raise ValueError(f"outcome row {i} missing opener_id/persona_slug")
        out.append(row)
    return out


def _print_report(report: Any, *, top: int, output_path: Path) -> None:
    print("\n" + "=" * 78)
    print("FIRST-TOUCH OPENER SIMULATION — RANKED BY DOWNSTREAM OUTCOME")
    print("=" * 78)
    print(f"workspace_id          : {report.workspace_id}")
    print(f"agent                 : {report.agent_name}")
    print(f"generator             : {report.generator}")
    print(f"persona panel ({len(report.persona_slugs)})     : {', '.join(report.persona_slugs)}")
    print(f"conversations/persona : {report.conversations_per_persona}")
    print(f"max turns             : {report.max_turns}")
    print(f"total conversations   : {report.total_conversations}")
    print(f"base seed             : {report.base_seed}")
    print(f"config fingerprint    : {report.config_fingerprint}")
    print(f"persisted artifact    : {output_path}")
    print("-" * 78)
    print(
        f"{'#':>2}  {'opener id':<24} {'score':>6} {'reply':>6} "
        f"{'engag':>6} {'agree':>6} {'intent':>7}"
    )
    print("-" * 78)
    for rank, agg in enumerate(report.rankings[:top], start=1):
        print(
            f"{rank:>2}. {agg.candidate.id:<24} {agg.mean_score:>6.1f} "
            f"{agg.reply_rate * 100:>5.0f}% {agg.engaged_rate * 100:>5.0f}% "
            f"{agg.agreed_rate * 100:>5.0f}% {agg.mean_buying_intent:>7.1f}"
        )

    if report.rankings:
        winner = report.rankings[0]
        print("\n" + "-" * 78)
        print("WINNER")
        print("-" * 78)
        print(f"id       : {winner.candidate.id}")
        print(f"strategy : {winner.candidate.strategy}")
        print(f"score    : {winner.mean_score}")
        if winner.agreed_packs:
            packs = ", ".join(f"{k}-pack x{v}" for k, v in sorted(winner.agreed_packs.items()))
            print(f"agreed   : {packs}")
        print(f"text     : {winner.candidate.text}")
    print("=" * 78 + "\n")


def main() -> int:
    ctx, args = bootstrap(
        description=__doc__,
        writes=False,
        default_env="local",
        logger_name="optimize_openers",
        configure=_configure,
    )
    return asyncio.run(_amain(ctx, args))


if __name__ == "__main__":
    raise SystemExit(run(main))
