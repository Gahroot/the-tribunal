"""Manual call HTTP boundary with provider stubs only (RF-008)."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db, get_workspace
from app.api.v1 import calls

WS_ID = uuid.uuid4()


def stub_app(monkeypatch: pytest.MonkeyPatch, call_status: str) -> tuple[FastAPI, SimpleNamespace]:
    """No lifespan, real DB, worker loops, or external calls."""
    app = FastAPI()
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = SimpleNamespace(workspace_id=WS_ID)
    db.execute.return_value = result
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, is_active=True)
    app.dependency_overrides[get_workspace] = lambda: SimpleNamespace(id=WS_ID)
    message = SimpleNamespace(
        id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        direction="outbound",
        channel="voice",
        status=call_status,
        duration_seconds=None,
        recording_url=None,
        transcript=None,
        created_at=datetime.now(UTC),
        agent_id=None,
        is_ai=False,
        error_code="API_ERROR",
        error_message="raw provider dump with credentials",
    )
    provider = SimpleNamespace(initiate_call=AsyncMock(return_value=message), close=AsyncMock())
    monkeypatch.setattr(calls.settings, "telnyx_api_key", "test-only")
    monkeypatch.setattr(calls, "TelnyxVoiceService", lambda *_: provider)
    app.include_router(calls.router, prefix="/api/v1/workspaces/{workspace_id}/calls")
    return app, provider


@pytest.mark.parametrize("call_status", ["failed", "queued", "ringing", "completed"])
async def test_manual_call_status(monkeypatch: pytest.MonkeyPatch, call_status: str) -> None:
    app, provider = stub_app(monkeypatch, call_status)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/workspaces/{WS_ID}/calls",
            json={"to_number": "+15551230000", "from_phone_number": "+15550001111"},
        )
    if call_status in {"ringing", "completed"}:
        assert response.status_code == 201
        assert response.json()["status"] == call_status
    else:
        assert response.status_code == 502
        assert "Call was not accepted" in response.json()["detail"]
        assert "try again" in response.json()["detail"]
        assert "credentials" not in response.text
    provider.close.assert_awaited_once()


async def test_manual_missing_configuration_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    app, provider = stub_app(monkeypatch, "ringing")
    monkeypatch.setattr(calls.settings, "telnyx_api_key", "")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/workspaces/{WS_ID}/calls",
            json={"to_number": "+15551230000", "from_phone_number": "+15550001111"},
        )
    assert response.status_code == 503
    assert response.json()["detail"] == "Telnyx not configured"
    provider.initiate_call.assert_not_awaited()
