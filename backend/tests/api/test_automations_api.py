"""Automation API boundary tests (RF-013).

Active automations must be fully configured; drafts may be incomplete but are
reported as such; updates preserve stored configuration. DB is mocked.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db, get_workspace
from app.api.v1 import automations as automations_module
from app.main import http_exception_handler
from app.models.automation import Automation

WS_ID = uuid.uuid4()
BASE = f"/api/v1/workspaces/{WS_ID}/automations"

DEFAULT_SMS_DRAFT: dict[str, Any] = {
    "name": "No-show follow-up",
    "trigger_type": "no_show",
    "trigger_config": {},
    "actions": [{"type": "send_sms", "config": {}}],
}


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


def _stored_automation(**overrides: Any) -> Automation:
    now = datetime.now(UTC)
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "workspace_id": WS_ID,
        "name": "Tag follow-up",
        "description": None,
        "trigger_type": "contact_tagged",
        "trigger_config": {"tag": "hot-lead"},
        "actions": [
            {"type": "send_sms", "config": {"message": "Hi {first_name}"}},
            {"type": "apply_tag", "config": {"tag": "texted"}},
        ],
        "is_active": False,
        "last_triggered_at": None,
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return Automation(**values)


def _scalar_result(value: Any) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalars.return_value.all.return_value = []
    return result


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()

    async def _refresh(obj: Automation) -> None:
        now = datetime.now(UTC)
        obj.id = obj.id or uuid.uuid4()
        obj.created_at = obj.created_at or now
        obj.updated_at = now

    db.refresh = AsyncMock(side_effect=_refresh)
    db.execute = AsyncMock(return_value=_scalar_result(None))
    # Referenced campaigns/agents exist unless a test says otherwise.
    db.scalar = AsyncMock(return_value=uuid.uuid4())
    return db


@pytest.fixture
async def client(mock_db: AsyncMock) -> AsyncIterator[AsyncClient]:
    app = FastAPI(lifespan=_lifespan)
    # Production handler: structured ``{code, message, details}`` errors.
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]

    async def override_db() -> AsyncIterator[AsyncMock]:
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_workspace] = lambda: MagicMock(id=WS_ID)
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id=1, is_active=True)
    app.include_router(
        automations_module.router, prefix="/api/v1/workspaces/{workspace_id}/automations"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_default_sms_automation_cannot_be_created_active(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    response = await client.post(BASE, json={**DEFAULT_SMS_DRAFT, "is_active": True})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "automation_incomplete"
    assert "text message" in body["message"]
    assert body["details"]["issues"] == [
        {
            "code": "missing_sms_message",
            "field": "actions[0].config.message",
            "message": "Step 1: write the text message to send.",
        }
    ]
    mock_db.add.assert_not_called()
    mock_db.commit.assert_not_awaited()


async def test_incomplete_automation_saves_as_draft_and_reports_issues(
    client: AsyncClient,
) -> None:
    response = await client.post(BASE, json={**DEFAULT_SMS_DRAFT, "is_active": False})

    assert response.status_code == 201
    body = response.json()
    assert body["is_active"] is False
    assert body["readiness"] == "incomplete"
    assert [i["code"] for i in body["config_issues"]] == ["missing_sms_message"]
    assert body["last_execution"] is None


async def test_configured_default_sms_automation_is_ready_and_active(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    payload = {
        **DEFAULT_SMS_DRAFT,
        "actions": [{"type": "send_sms", "config": {"message": "Hi {first_name}"}}],
        "is_active": True,
    }
    response = await client.post(BASE, json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["is_active"] is True
    assert body["readiness"] == "ready"
    assert body["config_issues"] == []
    assert body["actions"] == payload["actions"]
    stored: Automation = mock_db.add.call_args.args[0]
    assert stored.actions == payload["actions"]


async def test_activation_rejects_campaign_from_other_workspace(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.scalar = AsyncMock(return_value=None)
    payload = {
        "name": "Enroll",
        "trigger_type": "no_show",
        "actions": [{"type": "enroll_campaign", "config": {"campaign_id": str(uuid.uuid4())}}],
        "is_active": True,
    }

    response = await client.post(BASE, json=payload)

    assert response.status_code == 422
    assert response.json()["details"]["issues"][0]["code"] == "campaign_not_found"


async def test_partial_update_preserves_trigger_config_and_all_actions(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    stored = _stored_automation()
    original_actions = [dict(a) for a in stored.actions]
    mock_db.execute = AsyncMock(return_value=_scalar_result(stored))

    response = await client.put(f"{BASE}/{stored.id}", json={"name": "Renamed"})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed"
    assert body["trigger_config"] == {"tag": "hot-lead"}
    assert body["actions"] == original_actions
    assert body["readiness"] == "ready"


async def test_null_fields_in_update_do_not_wipe_configuration(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    stored = _stored_automation()
    mock_db.execute = AsyncMock(return_value=_scalar_result(stored))

    response = await client.put(
        f"{BASE}/{stored.id}", json={"trigger_config": None, "actions": None}
    )

    assert response.status_code == 200
    assert stored.trigger_config == {"tag": "hot-lead"}
    assert len(stored.actions) == 2


async def test_activating_incomplete_stored_draft_is_rejected(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    stored = _stored_automation(actions=[{"type": "send_sms", "config": {}}])
    mock_db.execute = AsyncMock(return_value=_scalar_result(stored))

    update = await client.put(f"{BASE}/{stored.id}", json={"is_active": True})
    toggle = await client.post(f"{BASE}/{stored.id}/toggle")

    assert update.status_code == 422
    assert toggle.status_code == 422
    assert stored.is_active is False
    mock_db.commit.assert_not_awaited()


async def test_update_that_empties_an_active_automation_is_rejected(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    stored = _stored_automation(is_active=True)
    mock_db.execute = AsyncMock(return_value=_scalar_result(stored))

    response = await client.put(
        f"{BASE}/{stored.id}", json={"actions": [{"type": "send_sms", "config": {}}]}
    )

    assert response.status_code == 422
    assert stored.actions[0]["config"] == {"message": "Hi {first_name}"}


async def test_deactivating_always_allowed(client: AsyncClient, mock_db: AsyncMock) -> None:
    stored = _stored_automation(is_active=True, actions=[{"type": "send_sms", "config": {}}])
    mock_db.execute = AsyncMock(return_value=_scalar_result(stored))

    response = await client.post(f"{BASE}/{stored.id}/toggle")

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert response.json()["readiness"] == "incomplete"
