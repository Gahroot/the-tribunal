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

from app.api.deps import get_current_user, get_db, get_workspace
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
    app.include_router(
        credentials_module.router,
        prefix="/api/v1/workspaces/{workspace_id}/integrations",
    )
    return app


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
