"""Auth and behavior tests for the workspace autonomy-mandate API endpoints."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db, get_workspace, get_workspace_admin
from app.api.v1 import workspaces as workspaces_module

WS_ID = uuid.uuid4()


@asynccontextmanager
async def _test_lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


def _make_mock_workspace() -> MagicMock:
    ws = MagicMock()
    ws.id = WS_ID
    ws.is_active = True
    ws.autonomy_mandate = None  # exercise the normalize-from-empty path
    return ws


def _make_app(mock_db: AsyncMock, mock_workspace: MagicMock) -> FastAPI:
    app = FastAPI(lifespan=_test_lifespan)

    async def override_get_db() -> AsyncIterator[AsyncMock]:
        yield mock_db

    async def override_get_workspace() -> MagicMock:
        return mock_workspace

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_workspace] = override_get_workspace
    app.dependency_overrides[get_workspace_admin] = override_get_workspace
    app.include_router(
        workspaces_module.router,
        prefix="/api/v1/workspaces",
    )
    return app


@pytest.mark.asyncio
async def test_get_autonomy_mandate_returns_normalized_default() -> None:
    mock_db = AsyncMock()
    workspace = _make_mock_workspace()
    app = _make_app(mock_db, workspace)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/v1/workspaces/{WS_ID}/autonomy-mandate")

    assert resp.status_code == 200
    body = resp.json()
    assert body["posture"] == "act_and_report"
    assert body["auto_send_first_touches"] is True
    assert body["auto_close_batch_packs"] is True
    assert {pack["pack_key"] for pack in body["allowed_batch_packs"]} == {
        "sampler_100",
        "growth_300",
        "anchor_500",
        "scale_1000",
    }


@pytest.mark.asyncio
async def test_put_autonomy_mandate_persists_normalized_policy() -> None:
    mock_db = AsyncMock()
    workspace = _make_mock_workspace()
    app = _make_app(mock_db, workspace)

    payload = {
        "mandate": {
            "enabled": True,
            "posture": "act_and_report",
            "auto_send_first_touches": False,
            "auto_close_batch_packs": True,
            "daily_send_cap": 250,
            "batch_pack_max_price_cents": 399_700,
            "allowed_batch_packs": [
                {
                    "pack_key": "anchor_500",
                    "label": "500 ads",
                    "ad_count": 500,
                    "price_cents": 250_000,
                }
            ],
            "quiet_hours": {
                "enabled": True,
                "timezone": "America/New_York",
                "start": "21:00",
                "end": "07:00",
            },
            "escalation_rules": [
                {"key": "consulting", "label": "wants consulting", "keywords": ["consulting"]}
            ],
            "operator_report": {
                "enabled": True,
                "channel": "sms",
                "phone": "+14155551997",
                "events": ["payment_succeeded"],
            },
        }
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.put(
            f"/api/v1/workspaces/{WS_ID}/autonomy-mandate", json=payload
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["daily_send_cap"] == 250
    assert body["auto_send_first_touches"] is False
    assert [pack["pack_key"] for pack in body["allowed_batch_packs"]] == ["anchor_500"]
    assert body["operator_report"]["phone"] == "+14155551997"
    # The stored object is the normalized mandate, not the raw request.
    assert workspace.autonomy_mandate["version"] == 1
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_put_autonomy_mandate_rejects_out_of_bounds_send_cap() -> None:
    mock_db = AsyncMock()
    workspace = _make_mock_workspace()
    app = _make_app(mock_db, workspace)

    payload = {
        "mandate": {
            "daily_send_cap": 10_000_000,
            "allowed_batch_packs": [
                {
                    "pack_key": "anchor_500",
                    "label": "500 ads",
                    "ad_count": 500,
                    "price_cents": 250_000,
                }
            ],
        }
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.put(
            f"/api/v1/workspaces/{WS_ID}/autonomy-mandate", json=payload
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_autonomy_mandate_requires_at_least_one_pack() -> None:
    mock_db = AsyncMock()
    workspace = _make_mock_workspace()
    app = _make_app(mock_db, workspace)

    payload = {"mandate": {"allowed_batch_packs": []}}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.put(
            f"/api/v1/workspaces/{WS_ID}/autonomy-mandate", json=payload
        )

    assert resp.status_code == 422
