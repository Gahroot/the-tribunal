"""Shared contact memory guards and cross-channel prompt rendering."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from app.services.ai.contact_timeline import format_contact_timeline, record_event


@pytest.mark.asyncio
async def test_record_event_rejects_contact_outside_workspace():
    db = SimpleNamespace(scalar=AsyncMock(return_value=None), execute=AsyncMock())
    workspace_id = uuid.uuid4()
    await record_event(
        db,
        workspace_id=workspace_id,
        contact_id=17,
        source="crm_note",
        source_id="note-1",
        channel="crm",
        summary="Callback tomorrow",
        occurred_at=datetime.now(UTC),
    )
    db.execute.assert_not_awaited()
    lookup = str(db.scalar.await_args.args[0].compile(dialect=postgresql.dialect()))
    assert "contacts.workspace_id" in lookup and "contacts.id" in lookup


@pytest.mark.asyncio
async def test_record_event_uses_source_conflict_for_retries():
    db = SimpleNamespace(scalar=AsyncMock(return_value=17), execute=AsyncMock())
    await record_event(
        db,
        workspace_id=uuid.uuid4(),
        contact_id=17,
        source="message",
        source_id="sms-1",
        channel="sms",
        summary="inbound: Let's speak Thursday",
        occurred_at=datetime.now(UTC),
    )
    query = str(db.execute.await_args.args[0].compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT ON CONSTRAINT uq_contact_timeline_source DO UPDATE" in query


def test_timeline_keeps_channel_and_structured_post_call_facts_bounded():
    event = SimpleNamespace(
        channel="voice",
        occurred_at=datetime(2026, 9, 23, tzinfo=UTC),
        summary="Discussed scheduling",
        facts={
            "objections": ["Price"],
            "preferred_call_time": "Thursday afternoons",
            "callback_promise": "Agent promised a call on Thursday",
            "next_steps": ["Send the quote"],
        },
    )
    result = format_contact_timeline([event])
    assert "[voice 2026-09-23]" in result
    assert "Price" in result and "Thursday afternoons" in result
    assert "Agent promised" in result and "Send the quote" in result
    assert len(result) <= 2800
