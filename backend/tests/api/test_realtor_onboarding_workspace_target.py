"""Route tests for workspace-targeted realtor onboarding (RF-005).

The real ``get_workspace`` membership dependency runs; only the DB session,
current user, and service workflows are stubbed.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db
from app.api.v1.integrations import followupboss as fub_module
from app.api.v1.onboarding import realtor_setup as realtor_module
from app.models.workspace import Workspace, WorkspaceMembership
from app.services.onboarding.workspace_setup import (
    RealtorCampaignResult,
    RealtorOnboardingResult,
)

USER_ID = 7
SELECTED_WS = uuid.uuid4()
FOREIGN_WS = uuid.uuid4()

ONBOARD_BODY = {"calcom_api_key": "cal_key", "calcom_event_type_id": 123}


@asynccontextmanager
async def _test_lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


def _result(value: object | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _membership_db(member_of: set[uuid.UUID]) -> MagicMock:
    """DB stub that answers get_workspace's membership + workspace lookups."""
    db = MagicMock()
    pending: list[uuid.UUID] = []

    async def execute(statement: Any) -> MagicMock:
        sql = str(statement.compile(compile_kwargs={"literal_binds": True})).lower()
        if "workspace_memberships" in sql:
            for ws_id in member_of:
                if ws_id.hex in sql:
                    pending.append(ws_id)
                    return _result(
                        WorkspaceMembership(
                            id=uuid.uuid4(), user_id=USER_ID, workspace_id=ws_id, role="owner"
                        )
                    )
            return _result(None)
        if "from workspaces" in sql and pending:
            ws_id = pending.pop()
            return _result(Workspace(id=ws_id, name="Second", slug="second", is_active=True))
        raise AssertionError(f"unexpected query: {sql}")

    db.execute = AsyncMock(side_effect=execute)
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    return db


def _app(db: MagicMock) -> FastAPI:
    app = FastAPI(lifespan=_test_lifespan)

    async def override_get_db() -> AsyncIterator[MagicMock]:
        yield db

    user = MagicMock()
    user.id = USER_ID
    user.is_active = True
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    app.include_router(
        realtor_module.workspace_router, prefix="/api/v1/workspaces/{workspace_id}/realtor"
    )
    app.include_router(
        fub_module.workspace_router, prefix="/api/v1/workspaces/{workspace_id}/realtor"
    )
    app.include_router(fub_module.router, prefix="/api/v1/realtor")
    return app


async def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def onboarding_spy(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    async def fake(**kwargs: Any) -> RealtorOnboardingResult:
        return RealtorOnboardingResult(
            workspace_id=kwargs["workspace_id"],
            agent_id=uuid.uuid4(),
            phone_number_id=None,
            phone_number=None,
            calcom_connected=True,
        )

    spy = AsyncMock(side_effect=fake)
    monkeypatch.setattr(realtor_module, "complete_realtor_onboarding", spy)
    return spy


@pytest.fixture
def campaign_spy(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    async def fake(**kwargs: Any) -> RealtorCampaignResult:
        return RealtorCampaignResult(
            campaign_id=uuid.uuid4(),
            campaign_name="Lead Reactivation",
            campaign_status="running",
            contacts_imported=1,
            contacts_skipped=0,
            contacts_failed=0,
            phone_number_used="+15555550100",
            agent_id=uuid.uuid4(),
            started_at=None,
            workspace_id=kwargs["workspace_id"],
        )

    spy = AsyncMock(side_effect=fake)
    monkeypatch.setattr(realtor_module, "launch_realtor_campaign_from_csv", spy)
    return spy


async def test_onboard_targets_selected_workspace(onboarding_spy: AsyncMock) -> None:
    db = _membership_db({SELECTED_WS})
    async with await _client(_app(db)) as client:
        resp = await client.post(
            f"/api/v1/workspaces/{SELECTED_WS}/realtor/onboard", json=ONBOARD_BODY
        )

    assert resp.status_code == 201, resp.text
    assert resp.json()["workspace_id"] == str(SELECTED_WS)
    assert onboarding_spy.await_args.kwargs["workspace_id"] == SELECTED_WS
    assert resp.json()["phone_provisioned"] is False


async def test_onboard_rejects_non_member_without_default_fallback(
    onboarding_spy: AsyncMock,
) -> None:
    db = _membership_db({SELECTED_WS})
    async with await _client(_app(db)) as client:
        resp = await client.post(
            f"/api/v1/workspaces/{FOREIGN_WS}/realtor/onboard", json=ONBOARD_BODY
        )

    assert resp.status_code == 404
    onboarding_spy.assert_not_awaited()


async def test_campaign_targets_selected_workspace(campaign_spy: AsyncMock) -> None:
    db = _membership_db({SELECTED_WS})
    async with await _client(_app(db)) as client:
        resp = await client.post(
            f"/api/v1/workspaces/{SELECTED_WS}/realtor/campaigns",
            files={"file": ("leads.csv", b"first_name,phone_number\nAva,+15550000001\n")},
        )

    assert resp.status_code == 201, resp.text
    assert resp.json()["workspace_id"] == str(SELECTED_WS)
    assert campaign_spy.await_args.kwargs["workspace_id"] == SELECTED_WS


async def test_campaign_rejects_non_member(campaign_spy: AsyncMock) -> None:
    db = _membership_db({SELECTED_WS})
    async with await _client(_app(db)) as client:
        resp = await client.post(
            f"/api/v1/workspaces/{FOREIGN_WS}/realtor/campaigns",
            files={"file": ("leads.csv", b"first_name\n")},
        )

    assert resp.status_code == 404
    campaign_spy.assert_not_awaited()


async def test_legacy_fub_import_enforces_membership() -> None:
    db = _membership_db({SELECTED_WS})
    async with await _client(_app(db)) as client:
        resp = await client.post(
            "/api/v1/realtor/import-fub-contacts",
            json={"workspace_id": str(FOREIGN_WS), "import_all": True},
        )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Workspace not found or access denied"


async def test_scoped_fub_import_rejects_non_member() -> None:
    db = _membership_db({SELECTED_WS})
    async with await _client(_app(db)) as client:
        resp = await client.post(
            f"/api/v1/workspaces/{FOREIGN_WS}/realtor/import-fub-contacts",
            json={"import_all": True, "api_key": "fub_key"},
        )

    assert resp.status_code == 404
    db.commit.assert_not_awaited()
