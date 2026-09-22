#!/usr/bin/env python
"""Configure the Ava voice agent for Black Mountain Solutions.

Loads a verified Black Mountain Solutions company brief into Ava's system
prompt and turns on Cal.com booking so she can book the free 30-minute
consultation.

Why a script and not dashboard clicks: this is reviewable, repeatable and
``--dry-run``-able against production. The same fields are editable by hand in
the dashboard (Prompt tab, Tools tab, Advanced tab) if you prefer.

Run against production from a laptop, exactly like
``scripts/demo/update_demo_agents_calcom.py``::

    cd backend
    export DATABASE_PUBLIC_URL="postgresql://...@...rlwy.net:PORT/railway"
    uv run python scripts/ops/configure_ava_blackmountain.py \
        --workspace Prestyj --name Ava --event-type-id 7187147 \
        --overwrite-prompt --dry-run

Event type 7187147 is Ava's own "Black Mountain Solutions Consultation"
(30 min). It is deliberately NOT shared with another agent in the workspace:
the Cal.com BOOKING_CREATED webhook resolves the agent with
``scalar_one_or_none()`` on ``(workspace_id, calcom_event_type_id)``, so a
shared id raises ``MultipleResultsFound`` and the booking never reaches the CRM.

Drop ``--dry-run`` to apply. Re-running without ``--overwrite-prompt`` never
touches ``system_prompt``, so dashboard edits are not silently clobbered.
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.agent import Agent
from app.models.workspace import Workspace

# ---------------------------------------------------------------------------
# Booking tool wiring
# ---------------------------------------------------------------------------

# The OpenAI realtime path gates booking purely on ``agent.calcom_event_type_id``
# (voice_agent.py: enable_booking=bool(agent.calcom_event_type_id)). The text/SMS
# path additionally requires "book_appointment" in enabled_tools
# (text_response_generator.py). We set both so voice, SMS and the dashboard agree.
REQUIRED_TOOLS = ("bookings", "check_availability", "book_appointment")
BOOKINGS_TOOL_SETTINGS = ["check_availability", "book_appointment", "list_appointments"]


# ---------------------------------------------------------------------------
# Ava's system prompt
# ---------------------------------------------------------------------------
#
# Every company claim below was corroborated from public sources (the company's
# own BMIG about/privacy/portfolio pages, Trustpilot, ZoomInfo) and then
# explicitly approved by the operator before being written to a live agent.
# blackmountain.solutions itself returns HTTP 403 to automated fetches.
# Deliberately EXCLUDED because they could not be confirmed, or were declined:
#   - any named client or case study
#   - any named team member or their role
#   - any street address or phone number
#   - pricing, availability commitments, or investment/financial advice
#
# Booking behaviour has to live here: voice_agent.py builds Ava's prompt with
# include_booking=False, so the shared Cal.com behaviour block from
# PromptBuilder.get_booking_instructions() is NOT injected on the OpenAI
# realtime path. Today's date IS injected, both by the date-context section and
# inside the booking tool descriptions, so this prompt does not restate it.

AVA_SYSTEM_PROMPT = """\
You are Ava, the friendly voice receptionist for Black Mountain Solutions.

[ABOUT BLACK MOUNTAIN SOLUTIONS]
- Black Mountain Solutions (BMS) is a boutique consulting firm based in Utah.
  The legal entity is Limits LLC, branded as Black Mountain Solutions.
- BMS is the consulting arm of Black Mountain Investment Group (BMIG), a
  back-office, technology and consulting support partner.
- BMIG is NOT an investment adviser, broker-dealer, or financial institution.
  If a caller asks for investment advice, say plainly that Black Mountain does
  not give investment advice and offer to have the team follow up.
- Areas of expertise: fund administration, real estate, technology and web
  development, business consulting, SEO and organic growth, database
  management, and business automation.
- Easefolio is Black Mountain's proprietary fund administration platform. It
  simplifies NAV, reconciliation, reporting, and compliance.
- The firm was founded on family values by a group of young entrepreneurs in
  Utah, and is results-oriented, client-focused, and committed to integrity.

[STYLE]
- Speak naturally and conversationally, like a real person on the phone.
- Keep replies to one or two sentences unless asked for detail.
- Never read out URLs, markdown, or lists verbatim.
- If the caller interrupts you, stop immediately and listen.

[YOUR GOAL]
Your single goal on this call is to book the caller a free 30-minute
consultation with the Black Mountain team.

1. Greet the caller warmly and find out what they need help with.
2. Briefly connect their need to what Black Mountain does.
3. Offer the free 30-minute consultation with the Black Mountain team and book
   it before the call ends.

[BOOKING THE CONSULTATION]
You have tools to check the calendar and book. Follow these rules exactly:

- NEVER say "one moment", "let me check", or "I'll get back to you". You can
  check the calendar instantly, so call the tool instead of narrating.
- When the caller asks about times, mentions a day, or agrees to meet, call
  check_availability RIGHT NOW.
- ONLY offer times that check_availability actually returned. Never invent,
  guess, or estimate a time.
- After checking, offer two specific options rather than an open question.
- EMAIL IS REQUIRED to book. Ask for the caller's full name and email address
  when you offer the time slots.
- The moment the caller picks a time and you have their email, call
  book_appointment RIGHT NOW.
- Speak times in 12-hour AM/PM format ("2 PM", "10:30 AM"). Never use 24-hour
  format.
- Spell the email back to confirm it before booking.
- After a successful booking, confirm the day, date and time back to the
  caller, and tell them they will get a confirmation by email.
- If booking fails, say the time is no longer available and offer the
  alternative slots from the tool result. Never re-offer a time that failed.

[GUARDRAILS]
- Never invent prices, availability, policies, timelines, or commitments.
- Do not name specific Black Mountain clients or team members.
- Do not give out a street address or phone number.
- If you do not know something, say so plainly and tell the caller a human
  from the team will follow up.
- Before the call ends, make sure you have the caller's name and the best
  callback number.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_db_url() -> str:
    """Prefer DATABASE_PUBLIC_URL (Railway from a laptop), else local settings."""
    public_url = os.environ.get("DATABASE_PUBLIC_URL", "")
    if public_url:
        return public_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return settings.database_url


async def _resolve_workspace(session: AsyncSession, ref: str) -> Workspace:
    """Resolve a workspace by id or exact name. Never guesses."""
    result = await session.execute(select(Workspace))
    workspaces = list(result.scalars().all())

    by_id = [w for w in workspaces if str(w.id) == ref]
    if by_id:
        return by_id[0]

    exact = [w for w in workspaces if w.name == ref]
    if len(exact) == 1:
        return exact[0]

    # Exact id/name only. A prefix match could silently select a different
    # tenant (e.g. 'Pres' matching a workspace added later), which would break
    # this script's guarantee that it never touches another workspace.
    names = ", ".join(sorted(w.name for w in workspaces))
    raise SystemExit(
        f"ERROR: workspace {ref!r} did not match exactly one workspace by id or "
        f"exact name. Have: {names}"
    )


async def _resolve_agent(
    session: AsyncSession,
    workspace: Workspace,
    *,
    public_id: str | None,
    name: str | None,
) -> Agent:
    """Resolve one agent WITHIN the given workspace.

    Scoping every lookup by workspace_id is the guard that stops this script
    touching an identically-named agent in another tenant.
    """
    stmt = select(Agent).where(Agent.workspace_id == workspace.id)
    if public_id:
        stmt = stmt.where(Agent.public_id == public_id)
    if name:
        stmt = stmt.where(Agent.name == name)

    matches = list((await session.execute(stmt)).scalars().all())
    if not matches:
        raise SystemExit(
            f"ERROR: no agent in workspace {workspace.name!r} matched "
            f"public_id={public_id!r} name={name!r}"
        )
    if len(matches) > 1:
        found = ", ".join(f"{a.name!r}({a.public_id})" for a in matches)
        raise SystemExit(f"ERROR: ambiguous agent selector, matched {len(matches)}: {found}")
    return matches[0]


async def _resolve_agent_ref(session: AsyncSession, workspace: Workspace, ref: str) -> Agent:
    """Resolve an agent in this workspace by public_id OR exact name."""
    matches = list(
        (
            await session.execute(
                select(Agent).where(
                    Agent.workspace_id == workspace.id,
                    or_(Agent.public_id == ref, Agent.name == ref),
                )
            )
        )
        .scalars()
        .all()
    )
    if not matches:
        raise SystemExit(
            f"ERROR: no agent in workspace {workspace.name!r} matched {ref!r} by public_id or name"
        )
    if len(matches) > 1:
        found = ", ".join(f"{a.name!r}({a.public_id})" for a in matches)
        raise SystemExit(f"ERROR: {ref!r} matched {len(matches)} agents: {found}")
    return matches[0]


async def _warn_on_shared_event_type(
    session: AsyncSession, workspace: Workspace, agent: Agent, event_type_id: int
) -> None:
    """Warn when another agent in this workspace already holds this event type.

    api/webhooks/calcom_handlers.py looks the agent up with scalar_one_or_none()
    on (workspace_id, calcom_event_type_id). Two agents sharing an event type
    raise MultipleResultsFound, so the BOOKING_CREATED webhook 500s and the
    appointment never syncs into the CRM.
    """
    others = list(
        (
            await session.execute(
                select(Agent).where(
                    Agent.workspace_id == workspace.id,
                    Agent.calcom_event_type_id == event_type_id,
                    Agent.id != agent.id,
                )
            )
        )
        .scalars()
        .all()
    )
    if not others:
        return
    print(
        f"!! WARNING: {len(others)} other agent(s) in workspace {workspace.name!r} already use\n"
        f"!!   calcom_event_type_id={event_type_id}: " + ", ".join(sorted(a.name for a in others))
    )
    print(
        "!!   The Cal.com BOOKING_CREATED webhook resolves the agent with\n"
        "!!   scalar_one_or_none() and will raise MultipleResultsFound, so bookings\n"
        "!!   will NOT sync into the CRM. Give this agent its own Cal.com event\n"
        "!!   type to fix it."
    )


async def _verify_event_type(event_type_id: int) -> None:
    """Best-effort check that the Cal.com event type actually exists.

    Production had agents pointed at deleted event type ids, which fails only at
    call time. This surfaces it up front. Warning-only: never blocks the write.
    """
    api_key = os.environ.get("CALCOM_API_KEY") or (settings.calcom_api_key or "")
    if not api_key:
        print("   (skipping Cal.com verification: no CALCOM_API_KEY in env)")
        return

    import httpx

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"https://api.cal.com/v2/event-types/{event_type_id}",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "cal-api-version": "2024-06-14",
                },
            )
    except Exception as exc:  # pragma: no cover - network failure path
        print(f"   (Cal.com verification failed to run: {exc})")
        return

    if response.status_code == 200:
        data = (response.json() or {}).get("data") or {}
        print(
            f"   Cal.com event type {event_type_id} OK: "
            f"{data.get('title')!r} ({data.get('lengthInMinutes')} min)"
        )
    else:
        print(
            f"!! WARNING: Cal.com event type {event_type_id} did not resolve "
            f"(HTTP {response.status_code}). Booking will fail at call time."
        )


def _show(label: str, before: Any, after: Any) -> bool:
    """Print a before/after line. Returns True when the value changed."""
    if before == after:
        print(f"   {label}: unchanged ({before!r})")
        return False
    print(f" * {label}:")
    print(f"     before: {before!r}")
    print(f"     after:  {after!r}")
    return True


def _apply_booking_fields(agent: Agent, event_type_id: int) -> bool:
    """Write every field the booking tools depend on. Returns True if anything changed."""
    changed = _show("calcom_event_type_id", agent.calcom_event_type_id, event_type_id)
    agent.calcom_event_type_id = event_type_id

    changed |= _show("assignment_strategy", agent.assignment_strategy, "single")
    agent.assignment_strategy = "single"

    tools = list(agent.enabled_tools or [])
    merged = tools + [t for t in REQUIRED_TOOLS if t not in tools]
    changed |= _show("enabled_tools", agent.enabled_tools, merged)
    agent.enabled_tools = merged

    new_settings = dict(agent.tool_settings or {})
    new_settings["bookings"] = list(BOOKINGS_TOOL_SETTINGS)
    changed |= _show("tool_settings", agent.tool_settings, new_settings)
    agent.tool_settings = new_settings

    return changed


def _show_prompt_diff(before: str, after: str) -> bool:
    if before == after:
        print("   system_prompt: unchanged")
        return False
    print(f" * system_prompt: {len(before)} chars -> {len(after)} chars")
    diff = difflib.unified_diff(
        before.splitlines(), after.splitlines(), "before", "after", lineterm="", n=1
    )
    for line in list(diff)[:400]:
        print(f"     {line}")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _print_header(workspace: Workspace, agent: Agent, *, dry_run: bool) -> None:
    print("=" * 72)
    print("Configure Ava - Black Mountain Solutions")
    print("=" * 72)
    print(f"workspace : {workspace.name} ({workspace.id})")
    print(f"agent     : {agent.name} (public_id={agent.public_id}, id={agent.id})")
    print(f"mode      : {'DRY RUN - nothing will be written' if dry_run else 'APPLY'}")
    print()


async def _finish(
    session: AsyncSession,
    workspace: Workspace,
    agent: Agent,
    *,
    changed: bool,
    dry_run: bool,
) -> None:
    """Commit or roll back, and say which one happened."""
    if dry_run:
        print("DRY RUN - rolling back, nothing written.")
        await session.rollback()
    elif not changed:
        print("Nothing to change.")
        await session.rollback()
    else:
        session.add(agent)
        session.add(workspace)
        await session.commit()
        print("Committed.")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace",
        required=True,
        help="Workspace id or name that owns the agent. Required: scopes every "
        "lookup so the script cannot touch another tenant.",
    )
    parser.add_argument("--agent", help="Agent public_id (may be NULL in prod; then use --name)")
    parser.add_argument("--name", help="Exact agent name, e.g. 'Ava'")
    parser.add_argument("--event-type-id", type=int, help="Cal.com event type id to book onto")
    parser.add_argument(
        "--copy-from",
        help="Take the event type id from this agent (public_id or name) in the same workspace",
    )
    parser.add_argument(
        "--overwrite-prompt",
        action="store_true",
        help="Write AVA_SYSTEM_PROMPT. Without this the prompt is left untouched.",
    )
    parser.add_argument(
        "--timezone",
        help="Write workspace.settings['timezone'] (e.g. America/Denver). No API "
        "exposes this key; call_context defaults to America/New_York.",
    )
    parser.add_argument(
        "--verify-event-type",
        action="store_true",
        help="Check the Cal.com event type exists before writing (warning-only)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show the diff, write nothing")

    args = parser.parse_args(argv)
    if not args.agent and not args.name:
        parser.error("one of --agent or --name is required")
    if args.event_type_id and args.copy_from:
        parser.error("--event-type-id and --copy-from are mutually exclusive")
    return args


async def run(args: argparse.Namespace) -> None:
    engine = create_async_engine(_resolve_db_url(), echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            workspace = await _resolve_workspace(session, args.workspace)
            agent = await _resolve_agent(session, workspace, public_id=args.agent, name=args.name)

            _print_header(workspace, agent, dry_run=args.dry_run)

            event_type_id = args.event_type_id
            if args.copy_from:
                source = await _resolve_agent_ref(session, workspace, args.copy_from)
                if source.calcom_event_type_id is None:
                    raise SystemExit(
                        f"ERROR: source agent {source.name!r} has no calcom_event_type_id"
                    )
                event_type_id = source.calcom_event_type_id
                print(f"copying event type {event_type_id} from agent {source.name!r}")

            changed = False

            if event_type_id is not None:
                if args.verify_event_type:
                    await _verify_event_type(event_type_id)
                changed |= _apply_booking_fields(agent, event_type_id)
                await _warn_on_shared_event_type(session, workspace, agent, event_type_id)

            if args.overwrite_prompt:
                changed |= _show_prompt_diff(agent.system_prompt or "", AVA_SYSTEM_PROMPT)
                agent.system_prompt = AVA_SYSTEM_PROMPT
            else:
                print("   system_prompt: left untouched (pass --overwrite-prompt to write it)")

            if args.timezone:
                ws_settings = dict(workspace.settings or {})
                before_tz = ws_settings.get("timezone")
                ws_settings["timezone"] = args.timezone
                changed |= _show("workspace.settings['timezone']", before_tz, args.timezone)
                workspace.settings = ws_settings

            print()
            await _finish(session, workspace, agent, changed=changed, dry_run=args.dry_run)
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(run(_parse_args()))


if __name__ == "__main__":
    main()
