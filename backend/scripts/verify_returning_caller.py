"""Runtime check: returning-caller recognition + cross-call memory.

Seeds (against the LOCAL dev DB) a contact with a prior completed call and a
stored caller memory, then runs the exact inbound call-start path
(``lookup_call_context``) and prints whether a returning-caller recap was
injected — proving detection + real pgvector memory retrieval end to end.

Run: ``uv run python scripts/verify_returning_caller.py``
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import structlog

from app.db.session import AsyncSessionLocal
from app.models.caller_memory import CallerMemory
from app.models.contact import Contact
from app.models.conversation import Conversation, Message
from app.models.workspace import Workspace
from app.services.ai.call_context import lookup_call_context

log = structlog.get_logger().bind(check="verify_returning_caller")


async def main() -> None:
    call_control_id = f"verify-returning-{uuid.uuid4().hex[:8]}"

    async with AsyncSessionLocal() as db:
        ws = (await db.execute(Workspace.__table__.select().limit(1))).first()
        workspace_id = ws.id
        contact = (
            await db.execute(
                Contact.__table__.select().where(Contact.workspace_id == workspace_id).limit(1)
            )
        ).first()
        contact_id = contact.id
        log.info("seed_target", workspace_id=str(workspace_id), contact_id=contact_id)

        now = datetime.now(UTC)
        conversation = Conversation(
            workspace_id=workspace_id,
            contact_id=contact_id,
            workspace_phone="+15550000001",
            contact_phone="+15550000002",
            channel="voice",
            ai_enabled=True,
            last_message_at=now,
            last_message_direction="inbound",
            last_message_preview="Incoming call",
        )
        db.add(conversation)
        await db.flush()

        # A prior COMPLETED voice call (makes the caller "returning").
        prior = Message(
            conversation_id=conversation.id,
            provider_message_id=f"{call_control_id}-prior",
            direction="inbound",
            channel="voice",
            body="",
            status="completed",
            created_at=now - timedelta(days=3),
        )
        # The CURRENT inbound call (what lookup_call_context resolves).
        current = Message(
            conversation_id=conversation.id,
            provider_message_id=call_control_id,
            direction="inbound",
            channel="voice",
            body="",
            status="ringing",
        )
        db.add_all([prior, current])

        # A stored cross-call memory (dummy embedding to avoid an OpenAI call).
        db.add(
            CallerMemory(
                workspace_id=workspace_id,
                contact_id=contact_id,
                conversation_id=conversation.id,
                message_id=prior.id,
                summary="Caller asked about premium pricing and wanted a callback Friday.",
                direction="inbound",
                embedding=[0.1] * 1536,
                occurred_at=now - timedelta(days=3),
            )
        )
        await db.commit()
        log.info("seed_committed", call_control_id=call_control_id)

    # Exact inbound call-start path.
    context = await lookup_call_context(call_control_id, log)
    returning = (context.contact_info or {}).get("returning_summary")
    log.info(
        "lookup_result",
        has_contact=bool(context.contact_info),
        returning_caller=context.metadata.get("returning_caller"),
        returning_summary_present=bool(returning),
    )
    if returning:
        log.info("returning_summary_text", text=returning)
        print("\n=== RETURNING SUMMARY INJECTED ===")
        print(returning)
    else:
        print("\n!!! NO RETURNING SUMMARY (unexpected) !!!")

    # Cleanup seeded rows.
    async with AsyncSessionLocal() as db:
        await db.execute(
            CallerMemory.__table__.delete().where(CallerMemory.conversation_id == conversation.id)
        )
        await db.execute(
            Message.__table__.delete().where(Message.conversation_id == conversation.id)
        )
        await db.execute(Conversation.__table__.delete().where(Conversation.id == conversation.id))
        await db.commit()
        log.info("seed_cleaned_up")


if __name__ == "__main__":
    asyncio.run(main())
