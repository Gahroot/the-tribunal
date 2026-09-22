#!/usr/bin/env python3
"""Seed a GPT Live (gpt-realtime-2.1) inbound voice agent and bind it to a number.

Idempotent: re-running updates the existing agent rather than creating a second
one, and re-points the phone number's assigned agent.

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
from app.services.ai.openai_realtime_config import DEFAULT_GPT_LIVE_MODEL

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


async def main(workspace_id: uuid.UUID, phone: str, model: str) -> None:
    async with AsyncSessionLocal() as db:
        existing = await db.execute(
            select(Agent).where(
                Agent.workspace_id == workspace_id,
                Agent.name == AGENT_NAME,
            )
        )
        agent = existing.scalar_one_or_none()

        if agent is None:
            agent = Agent(workspace_id=workspace_id, name=AGENT_NAME)
            db.add(agent)
            action = "created"
        else:
            action = "updated"

        agent.description = "Inbound voice receptionist on the GPT Live realtime model."
        agent.voice_provider = "openai"
        agent.realtime_model = model
        agent.reasoning_effort = "low"
        agent.voice_id = "marin"
        agent.language = "en-US"
        agent.system_prompt = SYSTEM_PROMPT
        agent.initial_greeting = GREETING
        agent.channel_mode = "voice"
        agent.turn_detection_mode = "semantic_vad"
        agent.is_active = True

        await db.flush()

        number = await db.execute(
            select(PhoneNumber).where(
                PhoneNumber.workspace_id == workspace_id,
                PhoneNumber.phone_number == phone,
            )
        )
        pn = number.scalar_one_or_none()
        if pn is None:
            raise SystemExit(f"phone number {phone} not found in workspace {workspace_id}")

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
    args = ap.parse_args()
    asyncio.run(main(uuid.UUID(args.workspace), args.phone, args.model))
