"""Settings integrations endpoint contract test.

Verifies that the workspace integrations status list surfaces Follow Up Boss
alongside the other known providers, so it has a durable management surface in
Settings -> Integrations (RF-006). DB-free via dependency overrides.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db, get_workspace, get_workspace_admin
from app.api.v1 import settings as settings_module
from app.api.v1.integrations import credentials as credentials_module

WS_ID = uuid.uuid4()


@asynccontextmanager
async def _test_lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


def _make_mock_workspace() -> MagicMock:
    ws = MagicMock()
    ws.id = WS_ID
    ws.is_active = True
    return ws


def _make_mock_user() -> MagicMock:
    user = MagicMock()
    user.id = 1
    user.is_active = True
    return user


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    # get_integrations iterates result.scalars().all(); no rows -> nothing connected.
    scalars = MagicMock()
    scalars.all.return_value = []
    result = MagicMock()
    result.scalars.return_value = scalars
    db.execute = AsyncMock(return_value=result)
    return db


def _auth_app(mock_db: AsyncMock) -> FastAPI:
    app = FastAPI(lifespan=_test_lifespan)

    async def override_get_db() -> AsyncIterator[AsyncMock]:
        yield mock_db

    async def override_get_workspace() -> MagicMock:
        return _make_mock_workspace()

    async def override_get_current_user() -> MagicMock:
        return _make_mock_user()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_workspace] = override_get_workspace
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.include_router(settings_module.router, prefix="/api/v1")
    return app


@pytest.fixture
async def auth_client(mock_db: AsyncMock) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=_auth_app(mock_db)),
        base_url="http://testserver",
    ) as ac:
        yield ac


async def test_integrations_list_includes_followupboss(auth_client: AsyncClient) -> None:
    resp = await auth_client.get(f"/api/v1/workspaces/{WS_ID}/integrations")
    assert resp.status_code == 200

    integrations = resp.json()["integrations"]
    by_type = {i["integration_type"]: i for i in integrations}

    assert "followupboss" in by_type, "Follow Up Boss must be a known integration"
    fub = by_type["followupboss"]
    assert fub["display_name"] == "Follow Up Boss"
    assert fub["description"] == "Lead CRM sync"
    assert fub["is_connected"] is False


def _credentials_app(mock_db: AsyncMock) -> FastAPI:
    """Mount the integrations credentials router with overridden auth/db deps."""
    app = FastAPI(lifespan=_test_lifespan)

    async def override_get_db() -> AsyncIterator[AsyncMock]:
        yield mock_db

    async def override_get_workspace() -> MagicMock:
        return _make_mock_workspace()

    async def override_get_current_user() -> MagicMock:
        return _make_mock_user()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_workspace] = override_get_workspace
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_workspace_admin] = override_get_workspace
    app.include_router(
        credentials_module.router,
        prefix="/api/v1/workspaces/{workspace_id}/integrations",
    )
    return app


@pytest.mark.parametrize(
    ("strategy", "event_type", "staff_event", "staff_active", "expected"),
    [
        ("single", None, None, True, False),
        ("single", 42, None, True, True),
        ("single", None, 43, True, False),
        ("round_robin", None, 43, True, True),
        ("skill_based", None, 43, True, True),
        ("round_robin", None, None, True, False),
        ("round_robin", None, 43, False, False),
        ("skill_based", 42, None, True, True),
    ],
)
async def test_default_agent_booking_readiness(
    mock_db, strategy, event_type, staff_event, staff_active, expected
):
    from app.core.encryption import encrypt_json
    from app.models.workspace import WorkspaceIntegration

    integration = WorkspaceIntegration(
        workspace_id=WS_ID,
        integration_type="calcom",
        is_active=True,
        encrypted_credentials=encrypt_json({"api_key": "local-fixture-key"}),
    )
    agent = SimpleNamespace(
        id=uuid.uuid4(), assignment_strategy=strategy, calcom_event_type_id=event_type
    )
    staff = SimpleNamespace(
        name="Fixture",
        skills=["sales"],
        is_active=staff_active,
        calcom_event_type_id=staff_event,
        priority=0,
        assignment_count=0,
        last_assigned_at=None,
    )
    credential_result = MagicMock()
    credential_result.scalar_one_or_none.return_value = integration
    agent_result = MagicMock()
    agent_result.scalar_one_or_none.return_value = agent
    staff_result = MagicMock()
    staff_result.scalars.return_value.all.return_value = [staff]
    mock_db.execute.side_effect = [credential_result, agent_result, staff_result]
    async with AsyncClient(
        transport=ASGITransport(app=_credentials_app(mock_db)), base_url="http://testserver"
    ) as client:
        response = await client.get(
            f"/api/v1/workspaces/{WS_ID}/integrations/calcom/booking-readiness"
        )
    assert response.status_code == 200
    assert response.json()["ready"] is expected
    assert response.json()["href"] == f"/agents/{agent.id}?setup=calendar"
    assert "local-fixture-key" not in response.text
    mock_db.commit.assert_not_called()
    # Every lookup is restricted to this workspace; staff additionally to the agent.
    for call in mock_db.execute.call_args_list:
        assert WS_ID in call.args[0].compile().params.values()


@pytest.mark.parametrize("credentials", [None, {}, {"api_key": "   "}])
async def test_calendar_readiness_requires_usable_credentials(mock_db, monkeypatch, credentials):
    from app.core.config import settings
    from app.core.encryption import encrypt_json
    from app.models.workspace import WorkspaceIntegration

    monkeypatch.setattr(settings, "calcom_api_key", "")
    result = MagicMock()
    result.scalar_one_or_none.return_value = (
        None
        if credentials is None
        else WorkspaceIntegration(
            workspace_id=WS_ID,
            integration_type="calcom",
            is_active=True,
            encrypted_credentials=encrypt_json(credentials),
        )
    )
    mock_db.execute.return_value = result
    async with AsyncClient(
        transport=ASGITransport(app=_credentials_app(mock_db)), base_url="http://testserver"
    ) as client:
        response = await client.get(
            f"/api/v1/workspaces/{WS_ID}/integrations/calcom/booking-readiness"
        )
    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert response.json()["href"] == "/settings?tab=integrations"


async def test_calendar_readiness_does_not_turn_database_failure_into_incomplete(mock_db):
    mock_db.execute.side_effect = RuntimeError("Fixture database unavailable")
    async with AsyncClient(
        transport=ASGITransport(app=_credentials_app(mock_db), raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            f"/api/v1/workspaces/{WS_ID}/integrations/calcom/booking-readiness"
        )
    assert response.status_code == 500


@pytest.mark.parametrize("state", ["brand", "managed", "disabled", "unreadable", "empty", "no_key"])
async def test_status_matches_outbound_account(auth_client, mock_db, monkeypatch, state):
    from app.core.config import settings
    from app.core.encryption import encrypt_json
    from app.models.workspace import WorkspaceIntegration

    monkeypatch.setattr(
        settings, "telnyx_api_key", "" if state in {"brand", "no_key"} else "platform-fixture"
    )
    record = WorkspaceIntegration(
        workspace_id=WS_ID,
        integration_type="telnyx",
        is_active=state != "disabled",
        encrypted_credentials="unreadable"
        if state == "unreadable"
        else encrypt_json({"api_key": "" if state == "empty" else "brand-fixture"}),
    )
    mock_db.execute.return_value.scalars.return_value.all.return_value = (
        [] if state in {"managed", "no_key"} else [record]
    )
    response = await auth_client.get(f"/api/v1/workspaces/{WS_ID}/integrations")
    assert response.status_code == 200
    status = next(
        item for item in response.json()["integrations"] if item["integration_type"] == "telnyx"
    )
    assert status["is_connected"] is (state == "brand")
    assert status["credential_source"] == (
        "workspace" if state == "brand" else "platform" if state == "managed" else "unavailable"
    )
    assert "brand-fixture" not in response.text
    assert "platform-fixture" not in response.text
    statement = mock_db.execute.call_args.args[0]
    assert WS_ID in statement.compile().params.values()


@pytest.mark.parametrize("provider", ["telnyx", "resend"])
async def test_disconnect_does_not_reactivate_managed_account(mock_db, provider):
    from app.core.encryption import encrypt_json
    from app.models.workspace import WorkspaceIntegration

    record = WorkspaceIntegration(
        workspace_id=WS_ID,
        integration_type=provider,
        is_active=True,
        encrypted_credentials=encrypt_json({"api_key": "fixture"}),
    )
    mock_db.execute.return_value.scalar_one_or_none.return_value = record
    async with AsyncClient(
        transport=ASGITransport(app=_credentials_app(mock_db)), base_url="http://testserver"
    ) as client:
        response = await client.delete(f"/api/v1/workspaces/{WS_ID}/integrations/{provider}")
    assert response.status_code == 204
    assert record.is_active is False
    assert record.safe_credentials() == {}
    mock_db.delete.assert_not_called()
    mock_db.commit.assert_awaited_once()


class _FakeAsyncClient:
    """Minimal httpx.AsyncClient stand-in returning a canned response."""

    def __init__(self, status_code: int, payload: dict) -> None:
        self._status_code = status_code
        self._payload = payload

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def get(self, *args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            status_code=self._status_code,
            json=lambda: self._payload,
        )


async def test_test_integration_validates_candidate_key_without_stored_row(
    mock_db: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pasted key is validated before saving: no stored row -> provider error, not 404."""
    # No stored integration row exists for this workspace.
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    # Telnyx rejects the bad key with 401; the test must surface that, not 404.
    monkeypatch.setattr(
        credentials_module.httpx,
        "AsyncClient",
        lambda *a, **k: _FakeAsyncClient(401, {}),
    )

    async with AsyncClient(
        transport=ASGITransport(app=_credentials_app(mock_db)),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.post(
            f"/api/v1/workspaces/{WS_ID}/integrations/telnyx/test",
            json={"credentials": {"api_key": "KEY_invalid"}},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "401" in body["message"]


async def test_test_integration_without_body_requires_stored_row(
    mock_db: AsyncMock,
) -> None:
    """Without candidate credentials and no stored row, the endpoint still 404s."""
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    async with AsyncClient(
        transport=ASGITransport(app=_credentials_app(mock_db)),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.post(
            f"/api/v1/workspaces/{WS_ID}/integrations/telnyx/test",
        )

    assert resp.status_code == 404


async def test_calcom_test_uses_booking_auth_and_reports_rejection(
    mock_db: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RF-011: Cal.com "Test" hits the same v2 Bearer auth booking uses; 401 is actionable."""
    seen: list[tuple[str, dict]] = []

    class _RecordingClient(_FakeAsyncClient):
        async def get(self, url: str, **kwargs: object) -> SimpleNamespace:  # type: ignore[override]
            seen.append((url, dict(kwargs.get("headers") or {})))  # type: ignore[call-overload]
            return await super().get(url, **kwargs)

    monkeypatch.setattr(
        credentials_module.httpx,
        "AsyncClient",
        lambda *a, **k: _RecordingClient(401, {}),
    )

    async with AsyncClient(
        transport=ASGITransport(app=_credentials_app(mock_db)),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.post(
            f"/api/v1/workspaces/{WS_ID}/integrations/calcom/test",
            json={"credentials": {"api_key": "cal_live_rejected"}},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "rejected" in body["message"]
    assert "cal_live_rejected" not in body["message"]
    assert seen[0][0] == "https://api.cal.com/v2/me"
    assert seen[0][1]["Authorization"] == "Bearer cal_live_rejected"
    assert seen[0][1]["cal-api-version"] == "2024-08-13"


async def test_stored_calcom_credentials_that_cannot_decrypt_are_reported(
    mock_db: AsyncMock,
) -> None:
    """RF-011: an undecryptable saved key returns guidance instead of a 500."""
    stored = MagicMock()
    stored.safe_credentials.return_value = None
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=stored))
    )

    async with AsyncClient(
        transport=ASGITransport(app=_credentials_app(mock_db)),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.post(f"/api/v1/workspaces/{WS_ID}/integrations/calcom/test")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "decrypted" in body["message"]
