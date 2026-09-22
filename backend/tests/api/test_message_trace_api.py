"""Auth/behavior tests for the message decision/trace read endpoints."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db, get_workspace
from app.api.v1 import conversations as conversations_module

WS_ID = uuid.uuid4()
CONVERSATION_ID = uuid.uuid4()
MESSAGE_ID = uuid.uuid4()
TRACE_ID = uuid.uuid4()


@asynccontextmanager
async def _test_lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


def _make_trace() -> MagicMock:
    trace = MagicMock()
    trace.id = TRACE_ID
    trace.workspace_id = WS_ID
    trace.conversation_id = CONVERSATION_ID
    trace.message_id = MESSAGE_ID
    trace.agent_id = None
    trace.prompt_version_id = None
    trace.generated_text = "The 500-pack is $2,500."
    trace.prompt = {"system_prompt": "You are the agent."}
    trace.knowledge_snippets = [{"title": "packs", "content": "500 = $2,500", "score": 0.9}]
    trace.model_params = {"model": "gpt-5.4-nano", "temperature": 0.3}
    trace.conversation_state = {"channel": "imessage", "last_inbound": None}
    trace.mandate = {"authorized_rule": "act_and_report.conversation_reply"}
    trace.created_at = datetime.now(UTC)
    return trace


def _make_app() -> FastAPI:
    app = FastAPI(lifespan=_test_lifespan)

    async def override_get_db() -> AsyncIterator[AsyncMock]:
        yield AsyncMock()

    async def override_get_workspace() -> MagicMock:
        ws = MagicMock()
        ws.id = WS_ID
        return ws

    async def override_get_current_user() -> MagicMock:
        return MagicMock(id=1)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_workspace] = override_get_workspace
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.include_router(
        conversations_module.router,
        prefix="/api/v1/workspaces/{workspace_id}/conversations",
    )
    return app


@pytest.mark.asyncio
async def test_get_message_trace_returns_decision_record(monkeypatch: pytest.MonkeyPatch) -> None:
    trace = _make_trace()
    monkeypatch.setattr(
        conversations_module.message_trace_service,
        "get_by_message",
        AsyncMock(return_value=trace),
    )
    app = _make_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/workspaces/{WS_ID}/conversations/messages/{MESSAGE_ID}/trace"
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(TRACE_ID)
    assert body["message_id"] == str(MESSAGE_ID)
    assert body["mandate"]["authorized_rule"] == "act_and_report.conversation_reply"
    assert body["knowledge_snippets"][0]["title"] == "packs"


@pytest.mark.asyncio
async def test_get_message_trace_404_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        conversations_module.message_trace_service,
        "get_by_message",
        AsyncMock(return_value=None),
    )
    app = _make_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/workspaces/{WS_ID}/conversations/messages/{MESSAGE_ID}/trace"
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_conversation_traces(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        conversations_module.message_trace_service,
        "list_by_conversation",
        AsyncMock(return_value=[_make_trace()]),
    )
    app = _make_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/workspaces/{WS_ID}/conversations/{CONVERSATION_ID}/traces"
        )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["conversation_id"] == str(CONVERSATION_ID)
