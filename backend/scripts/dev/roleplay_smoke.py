"""Local smoke test: drive a full rehearsal end-to-end against the real DB.

Stubs only the OpenAI boundary (no real key needed) and proves the practice
arena persists a COMPLETED, scored RehearsalRun with a transcript. Run with the
backend env vars set, e.g. via `uv run python scripts/roleplay_smoke.py`.
"""

import asyncio
import uuid

from app.db.session import AsyncSessionLocal
from app.models.agent import Agent
from app.models.workspace import Workspace
from app.services.ai.roleplay import roleplay_service as rs
from app.services.ai.roleplay.report_scorer import RehearsalReport


async def main() -> None:
    async with AsyncSessionLocal() as db:
        ws = Workspace(name=f"Roleplay Smoke {uuid.uuid4().hex[:6]}", slug=uuid.uuid4().hex[:10])
        db.add(ws)
        await db.flush()
        agent = Agent(
            workspace_id=ws.id,
            name="Smoke Closer",
            channel_mode="text",
            system_prompt="You are a friendly roofing rep. Book a free estimate.",
        )
        db.add(agent)
        await db.commit()

        # Stub the LLM boundary deterministically.
        async def fake_agent_reply(**_kwargs: object) -> str:
            return "Totally understand the concern — the estimate is free. Want a slot Tuesday?"

        async def fake_prospect_reply(**_kwargs: object) -> str:
            return "Hmm, okay, maybe. But how much does it usually cost?"

        async def fake_system_prompt(*_args: object, **_kwargs: object) -> str:
            return "SYSTEM PROMPT"

        async def fake_score(**_kwargs: object) -> RehearsalReport:
            return RehearsalReport(
                overall_score=78.0,
                objection_coverage=80.0,
                booking_attempted=True,
                tone_score=85.0,
                summary="Handled price concern and proposed a time.",
                strengths=["Acknowledged the objection", "Offered a concrete slot"],
                gaps=["Did not confirm email"],
                suggestions=["Add pricing ranges to the knowledge base"],
                scores={"tone_label": "warm", "booking_attempted": True},
            )

        rs.generate_agent_reply = fake_agent_reply  # type: ignore[assignment]
        rs.generate_prospect_reply = fake_prospect_reply  # type: ignore[assignment]
        rs.build_agent_system_prompt = fake_system_prompt  # type: ignore[assignment]
        rs.score_rehearsal = fake_score  # type: ignore[assignment]

        service = rs.RoleplayService(db)
        personas = await service.list_personas(ws.id)
        persona = personas[0]

        run = await service.create_run(
            ws.id,
            agent_id=agent.id,
            persona_id=persona.id,
            rehearsee="ai",
            max_turns=3,
        )

        print("RUN STATUS:", run.status)
        print("PERSONA:", run.persona_name)
        print("OVERALL SCORE:", run.overall_score)
        print("OBJECTION COVERAGE:", run.objection_coverage)
        print("BOOKING ATTEMPTED:", run.booking_attempted)
        print("TONE:", run.tone_score)
        print("TRANSCRIPT TURNS:", len(run.transcript))
        print("SUGGESTIONS:", run.suggestions)

        assert run.status.value == "completed", run.status
        assert run.overall_score == 78.0
        assert run.booking_attempted is True
        assert len(run.transcript) >= 6  # opening + 3 (agent+prospect) pairs
        print("\nSMOKE OK: scored rehearsal persisted with no tracebacks")

        # Cleanup
        await db.delete(run)
        await db.delete(agent)
        await db.delete(ws)
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
