#!/usr/bin/env python3
"""Seed a GPT Live (gpt-realtime-2.1) inbound voice agent and bind it to a number.

Idempotent: re-running updates the existing agent rather than creating a second
one, and re-points the phone number's assigned agent.

The existing agent is resolved by the number's current ``assigned_agent_id``
first, and only then by name. Operators rename agents in the dashboard, so a
name-only lookup silently creates a duplicate and steals the number away from
the customised original.

By default only unset fields are filled in, so dashboard edits to the prompt,
greeting or voice survive a re-run. Pass ``--overwrite`` to force the seeded
values back on.

Usage:
    cd backend && uv run python scripts/demo/seed_gpt_live_agent.py \
        --workspace <uuid> --phone +12485546801
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.agent import Agent
from app.models.phone_number import PhoneNumber
from app.services.ai.openai_realtime_config import (
    DEFAULT_GPT_LIVE_MODEL,
    model_supports_realtime_reasoning,
    normalize_realtime_model,
)

AGENT_NAME = "Ava | GPT Live"

SYSTEM_PROMPT = """You are Ava, a friendly and concise voice receptionist answering \
inbound phone calls.

Style:
- Speak naturally and conversationally, like a real person on the phone.
- Keep replies to one or two sentences unless asked for detail.
- Never read out URLs, markdown, or lists verbatim.
- If the caller interrupts you, stop immediately and listen.

Your job on this call:
1. Greet the caller warmly and ask how you can help.
2. Answer questions about the business clearly and honestly.
3. If you do not know something, say so plainly and offer to pass the message on.
4. Before the call ends, confirm the caller's name and the best callback number.

Never invent prices, availability, policies, or commitments. If the caller asks \
for something you cannot confirm, tell them a human will follow up."""

GREETING = "Hey, thanks for calling! This is Ava. How can I help you today?"


async def main(
    workspace_id: uuid.UUID,
    phone: str,
    model: str,
    overwrite: bool,
) -> None:
    # normalize_realtime_model() returns None for anything unsupported, which the
    # API path treats as "fall back to the global default". A seeding script must
    # not do that silently: a typo would leave the agent on the default model
    # while reporting success.
    resolved_model = normalize_realtime_model(model)
    if resolved_model is None:
        raise SystemExit(
            f"unsupported realtime model {model!r}; "
            f"expected a gpt-realtime-2.x id such as {DEFAULT_GPT_LIVE_MODEL}"
        )

    async with AsyncSessionLocal() as db:
        number = await db.execute(
            select(PhoneNumber).where(
                PhoneNumber.workspace_id == workspace_id,
                PhoneNumber.phone_number == phone,
            )
        )
        pn = number.scalar_one_or_none()
        if pn is None:
            raise SystemExit(f"phone number {phone} not found in workspace {workspace_id}")

        agent: Agent | None = None
        if pn.assigned_agent_id is not None:
            agent = await db.get(Agent, pn.assigned_agent_id)
            # Never write to another tenant's agent, even if the number carries a
            # stale cross-workspace assignment.
            if agent is not None and agent.workspace_id != workspace_id:
                raise SystemExit(
                    f"{phone} is assigned to agent {agent.id} in workspace "
                    f"{agent.workspace_id}, not {workspace_id}; refusing to modify it"
                )
        if agent is None:
            by_name = await db.execute(
                select(Agent).where(
                    Agent.workspace_id == workspace_id,
                    Agent.name == AGENT_NAME,
                )
            )
            agent = by_name.scalar_one_or_none()

        if agent is None:
            agent = Agent(workspace_id=workspace_id, name=AGENT_NAME)
            db.add(agent)
            action = "created"
        else:
            action = "updated"

        # Voice routing: always enforced, this is what the script exists to set.
        agent.voice_provider = "openai"
        agent.realtime_model = resolved_model
        # Only the gpt-realtime-2.x family accepts reasoning config; leave the
        # column at its "low" default for models that would reject it.
        if model_supports_realtime_reasoning(resolved_model):
            agent.reasoning_effort = "low"
        agent.channel_mode = "voice"
        agent.turn_detection_mode = "semantic_vad"
        agent.is_active = True

        # Content: preserve dashboard edits unless explicitly overwriting.
        for field, value in (
            ("description", "Inbound voice receptionist on the GPT Live realtime model."),
            ("system_prompt", SYSTEM_PROMPT),
            ("initial_greeting", GREETING),
            ("voice_id", "marin"),
            ("language", "en-US"),
        ):
            if overwrite or not getattr(agent, field, None):
                setattr(agent, field, value)

        await db.flush()

        pn.assigned_agent_id = agent.id
        pn.voice_enabled = True
        pn.is_active = True

        await db.commit()

        print(f"agent {action}: {agent.name} ({agent.id})")
        print(f"  realtime_model  = {agent.realtime_model}")
        print(f"  reasoning_effort= {agent.reasoning_effort}")
        print(f"  voice_id        = {agent.voice_id}")
        print(f"bound to {pn.phone_number} (assigned_agent_id={pn.assigned_agent_id})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--phone", required=True)
    ap.add_argument("--model", default=DEFAULT_GPT_LIVE_MODEL)
    ap.add_argument(
        "--overwrite",
        action="store_true",
        help="Force seeded prompt/greeting/voice back on, discarding dashboard edits.",
    )
    args = ap.parse_args()
    asyncio.run(main(uuid.UUID(args.workspace), args.phone, args.model, args.overwrite))
