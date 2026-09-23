"""Validation and auth tests for the nudges API endpoints.

Complements `test_nudges.py` by focusing on validation failures, auth failures,
and edge-case error paths rather than happy-path flows.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db, get_workspace
from app.api.v1 import nudges as nudges_module
from app.db.pagination import PaginationResult
from app.models.contact import Contact
from app.models.human_nudge import HumanNudge

WS_ID = uuid.uuid4()
NUDGE_ID = uuid.uuid4()


@asynccontextmanager
async def _test_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Minimal lifespan that skips workers, Redis, and DB setup."""
    yield


def _make_mock_workspace() -> MagicMock:
    """Build a mock Workspace."""
    ws = MagicMock()
    ws.id = WS_ID
    ws.is_active = True
    ws.settings = {"nudge_settings": {"enabled": True, "lead_days": 3}}
    return ws


def _make_mock_user() -> MagicMock:
    """Build a mock active User."""
    user = MagicMock()
    user.id = 1
    user.is_active = True
    user.email = "tester@example.com"
    return user


def _make_auth_test_app(
    mock_db: AsyncMock, mock_workspace: MagicMock, mock_user: MagicMock
) -> FastAPI:
    """Create test app with auth/workspace/db dependencies overridden."""
    app = FastAPI(lifespan=_test_lifespan)

    async def override_get_db() -> AsyncIterator[AsyncMock]:
        yield mock_db

    async def override_get_workspace() -> MagicMock:
        return mock_workspace

    async def override_get_current_user() -> MagicMock:
        return mock_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_workspace] = override_get_workspace
    app.dependency_overrides[get_current_user] = override_get_current_user

    app.include_router(
        nudges_module.router,
        prefix="/api/v1/workspaces/{workspace_id}/nudges",
    )
    app.include_router(
        nudges_module.settings_router,
        prefix="/api/v1/workspaces/{workspace_id}/nudge-settings",
    )
    return app


def _make_noauth_test_app() -> FastAPI:
    """Create a test app without dependency overrides (auth fails)."""
    app = FastAPI(lifespan=_test_lifespan)
    app.include_router(
        nudges_module.router,
        prefix="/api/v1/workspaces/{workspace_id}/nudges",
    )
    app.include_router(
        nudges_module.settings_router,
        prefix="/api/v1/workspaces/{workspace_id}/nudge-settings",
    )
    return app


@pytest.fixture
def mock_db() -> AsyncMock:
    """Async DB session mock."""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def mock_workspace() -> MagicMock:
    """Mock Workspace."""
    return _make_mock_workspace()


@pytest.fixture
def mock_user() -> MagicMock:
    """Mock User."""
    return _make_mock_user()


@pytest.fixture
async def client(
    mock_db: AsyncMock, mock_workspace: MagicMock, mock_user: MagicMock
) -> AsyncIterator[AsyncClient]:
    """Authenticated client (dependency overrides active)."""
    app = _make_auth_test_app(mock_db, mock_workspace, mock_user)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


@pytest.fixture
async def noauth_client() -> AsyncIterator[AsyncClient]:
    """Unauthenticated client (no overrides)."""
    app = _make_noauth_test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


class TestListNudgesAuth:
    """Auth and pagination validation for GET /nudges."""

    async def test_list_nudges_without_auth_returns_401(self, noauth_client: AsyncClient) -> None:
        """GET /nudges without auth returns 401."""
        response = await noauth_client.get(f"/api/v1/workspaces/{WS_ID}/nudges")
        assert response.status_code == 401

    async def test_list_nudges_invalid_page_returns_422(self, client: AsyncClient) -> None:
        """GET /nudges with page=0 (violates ge=1) returns 422."""
        response = await client.get(f"/api/v1/workspaces/{WS_ID}/nudges?page=0")
        assert response.status_code == 422

    async def test_list_nudges_page_size_over_limit_returns_422(self, client: AsyncClient) -> None:
        """GET /nudges with page_size=101 (violates le=100) returns 422."""
        response = await client.get(f"/api/v1/workspaces/{WS_ID}/nudges?page_size=101")
        assert response.status_code == 422

    async def test_list_nudges_negative_page_returns_422(self, client: AsyncClient) -> None:
        """GET /nudges with page=-1 returns 422."""
        response = await client.get(f"/api/v1/workspaces/{WS_ID}/nudges?page=-1")
        assert response.status_code == 422


class TestGetStatsAuth:
    """Auth for GET /nudges/stats."""

    async def test_get_stats_without_auth_returns_401(self, noauth_client: AsyncClient) -> None:
        """GET /nudges/stats without auth returns 401."""
        response = await noauth_client.get(f"/api/v1/workspaces/{WS_ID}/nudges/stats")
        assert response.status_code == 401


class TestActOnNudgeValidation:
    """Validation for PUT /nudges/{id}/act."""

    async def test_act_without_auth_returns_401(self, noauth_client: AsyncClient) -> None:
        """PUT /nudges/{id}/act without auth returns 401."""
        response = await noauth_client.put(f"/api/v1/workspaces/{WS_ID}/nudges/{NUDGE_ID}/act")
        assert response.status_code == 401

    async def test_act_invalid_nudge_uuid_returns_422(self, client: AsyncClient) -> None:
        """PUT /nudges/{id}/act with non-UUID nudge_id returns 422."""
        response = await client.put(f"/api/v1/workspaces/{WS_ID}/nudges/not-a-uuid/act")
        assert response.status_code == 422

    async def test_act_missing_nudge_returns_404(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """PUT /nudges/{id}/act with unknown nudge returns 404."""
        mock_result = MagicMock()
        mock_result.unique.return_value.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = await client.put(f"/api/v1/workspaces/{WS_ID}/nudges/{uuid.uuid4()}/act")
        assert response.status_code == 404


class TestDismissNudgeValidation:
    """Validation for PUT /nudges/{id}/dismiss."""

    async def test_dismiss_without_auth_returns_401(self, noauth_client: AsyncClient) -> None:
        """PUT /nudges/{id}/dismiss without auth returns 401."""
        response = await noauth_client.put(f"/api/v1/workspaces/{WS_ID}/nudges/{NUDGE_ID}/dismiss")
        assert response.status_code == 401

    async def test_dismiss_invalid_uuid_returns_422(self, client: AsyncClient) -> None:
        """PUT /nudges/{id}/dismiss with non-UUID returns 422."""
        response = await client.put(f"/api/v1/workspaces/{WS_ID}/nudges/abc/dismiss")
        assert response.status_code == 422

    async def test_dismiss_nonexistent_returns_404(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """PUT /nudges/{id}/dismiss with unknown id returns 404."""
        mock_result = MagicMock()
        mock_result.unique.return_value.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = await client.put(f"/api/v1/workspaces/{WS_ID}/nudges/{uuid.uuid4()}/dismiss")
        assert response.status_code == 404


class TestSnoozeNudgeValidation:
    """Validation for PUT /nudges/{id}/snooze."""

    async def test_snooze_without_auth_returns_401(self, noauth_client: AsyncClient) -> None:
        """PUT /nudges/{id}/snooze without auth returns 401."""
        response = await noauth_client.put(
            f"/api/v1/workspaces/{WS_ID}/nudges/{NUDGE_ID}/snooze",
            json={"snooze_until": datetime.now(UTC).isoformat()},
        )
        assert response.status_code == 401

    async def test_snooze_missing_body_returns_422(self, client: AsyncClient) -> None:
        """PUT /nudges/{id}/snooze without body returns 422."""
        response = await client.put(
            f"/api/v1/workspaces/{WS_ID}/nudges/{NUDGE_ID}/snooze",
        )
        assert response.status_code == 422

    async def test_snooze_missing_snooze_until_returns_422(self, client: AsyncClient) -> None:
        """PUT /nudges/{id}/snooze without snooze_until field returns 422."""
        response = await client.put(
            f"/api/v1/workspaces/{WS_ID}/nudges/{NUDGE_ID}/snooze",
            json={},
        )
        assert response.status_code == 422

    async def test_snooze_invalid_datetime_returns_422(self, client: AsyncClient) -> None:
        """PUT /nudges/{id}/snooze with invalid datetime returns 422."""
        response = await client.put(
            f"/api/v1/workspaces/{WS_ID}/nudges/{NUDGE_ID}/snooze",
            json={"snooze_until": "not-a-datetime"},
        )
        assert response.status_code == 422

    async def test_snooze_nonexistent_returns_404(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """PUT /nudges/{id}/snooze with unknown id returns 404."""
        mock_result = MagicMock()
        mock_result.unique.return_value.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        snooze_until = (datetime.now(UTC) + timedelta(hours=4)).isoformat()
        response = await client.put(
            f"/api/v1/workspaces/{WS_ID}/nudges/{uuid.uuid4()}/snooze",
            json={"snooze_until": snooze_until},
        )
        assert response.status_code == 404


def _make_contact_mock() -> Contact:
    """Build a real (transient) Contact for create-nudge responses."""
    return Contact(
        id=42,
        workspace_id=WS_ID,
        first_name="Ada",
        last_name="Lovelace",
        phone_number="+15550001111",
        company_name="Analytical Engines",
    )


def _make_mock_nudge_stub() -> HumanNudge:
    """Build a real (transient) HumanNudge for update-path tests."""
    return HumanNudge(
        id=NUDGE_ID,
        workspace_id=WS_ID,
        contact_id=1,
        nudge_type="follow_up",
        title="Send recap",
        message="Follow up on pricing",
        suggested_action=None,
        cta_label=None,
        href=None,
        priority="medium",
        due_date=datetime.now(UTC) + timedelta(days=2),
        source_date_field=None,
        status="pending",
        snoozed_until=None,
        delivered_via=None,
        delivered_at=None,
        acted_at=None,
        assigned_to_user_id=None,
        created_at=datetime.now(UTC),
        contact=Contact(
            id=1,
            workspace_id=WS_ID,
            first_name="Alice",
            last_name="Smith",
            phone_number="+15551234567",
        ),
    )


def _stamp_new_nudge(nudge: HumanNudge) -> None:
    """Apply the column defaults a real flush would set (mock db never flushes)."""
    if nudge.id is None:
        nudge.id = uuid.uuid4()
    if nudge.status is None:
        nudge.status = "pending"
    if nudge.created_at is None:
        nudge.created_at = datetime.now(UTC)


def _result_returning(value: object) -> MagicMock:
    """Build a mock execute() result whose scalar_one_or_none() is `value`."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


class TestCreateNudge:
    """Validation + happy path for POST /nudges."""

    async def test_create_without_auth_returns_401(self, noauth_client: AsyncClient) -> None:
        """POST /nudges without auth returns 401."""
        response = await noauth_client.post(
            f"/api/v1/workspaces/{WS_ID}/nudges",
            json={
                "contact_id": 42,
                "title": "Call back",
                "due_date": datetime.now(UTC).isoformat(),
            },
        )
        assert response.status_code == 401

    async def test_create_missing_title_returns_422(self, client: AsyncClient) -> None:
        """POST /nudges without a title returns 422."""
        response = await client.post(
            f"/api/v1/workspaces/{WS_ID}/nudges",
            json={"contact_id": 42, "due_date": datetime.now(UTC).isoformat()},
        )
        assert response.status_code == 422

    async def test_create_missing_due_date_returns_422(self, client: AsyncClient) -> None:
        """POST /nudges without a due_date returns 422."""
        response = await client.post(
            f"/api/v1/workspaces/{WS_ID}/nudges",
            json={"contact_id": 42, "title": "Call back"},
        )
        assert response.status_code == 422

    async def test_create_invalid_priority_returns_422(self, client: AsyncClient) -> None:
        """POST /nudges with an unknown priority returns 422."""
        response = await client.post(
            f"/api/v1/workspaces/{WS_ID}/nudges",
            json={
                "contact_id": 42,
                "title": "Call back",
                "due_date": datetime.now(UTC).isoformat(),
                "priority": "urgent",
            },
        )
        assert response.status_code == 422

    async def test_create_contact_not_found_returns_404(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """POST /nudges for a contact outside the workspace returns 404."""
        mock_db.execute = AsyncMock(return_value=_result_returning(None))

        response = await client.post(
            f"/api/v1/workspaces/{WS_ID}/nudges",
            json={
                "contact_id": 9999,
                "title": "Call back",
                "due_date": datetime.now(UTC).isoformat(),
            },
        )
        assert response.status_code == 404

    async def test_create_assignee_not_member_returns_422(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """Assigning a user outside the workspace fails closed with 422."""
        contact = _make_contact_mock()
        mock_db.execute = AsyncMock(
            side_effect=[_result_returning(contact), _result_returning(None)]
        )

        response = await client.post(
            f"/api/v1/workspaces/{WS_ID}/nudges",
            json={
                "contact_id": contact.id,
                "title": "Call back",
                "due_date": datetime.now(UTC).isoformat(),
                "assigned_to_user_id": 777,
            },
        )
        assert response.status_code == 422
        assert "not a workspace member" in response.json()["detail"]

    async def test_create_success_returns_201(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """POST /nudges creates a pending follow-up and returns it with contact fields."""
        contact = _make_contact_mock()
        mock_db.execute = AsyncMock(return_value=_result_returning(contact))
        mock_db.add = MagicMock(side_effect=_stamp_new_nudge)

        due = datetime.now(UTC) + timedelta(days=1)
        response = await client.post(
            f"/api/v1/workspaces/{WS_ID}/nudges",
            json={
                "contact_id": contact.id,
                "title": "Send recap",
                "message": "Follow up on pricing",
                "due_date": due.isoformat(),
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["title"] == "Send recap"
        assert body["contact_id"] == contact.id
        assert body["nudge_type"] == "follow_up"
        assert body["priority"] == "medium"
        assert body["status"] == "pending"
        assert body["contact_name"] == "Ada Lovelace"
        mock_db.commit.assert_awaited_once()
        created = mock_db.add.call_args.args[0]
        assert created.contact_id == contact.id


class TestUpdateNudge:
    """Validation + happy path for PUT /nudges/{id}."""

    async def test_update_without_auth_returns_401(self, noauth_client: AsyncClient) -> None:
        """PUT /nudges/{id} without auth returns 401."""
        response = await noauth_client.put(
            f"/api/v1/workspaces/{WS_ID}/nudges/{NUDGE_ID}",
            json={"due_date": datetime.now(UTC).isoformat()},
        )
        assert response.status_code == 401

    async def test_update_invalid_nudge_uuid_returns_422(self, client: AsyncClient) -> None:
        """PUT /nudges/{id} with a non-UUID id returns 422."""
        response = await client.put(
            f"/api/v1/workspaces/{WS_ID}/nudges/not-a-uuid",
            json={"due_date": datetime.now(UTC).isoformat()},
        )
        assert response.status_code == 422

    async def test_update_invalid_priority_returns_422(self, client: AsyncClient) -> None:
        """PUT /nudges/{id} with an unknown priority returns 422."""
        response = await client.put(
            f"/api/v1/workspaces/{WS_ID}/nudges/{NUDGE_ID}",
            json={"priority": "urgent"},
        )
        assert response.status_code == 422

    async def test_update_missing_nudge_returns_404(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """PUT /nudges/{id} with unknown id returns 404."""
        mock_result = MagicMock()
        mock_result.unique.return_value.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = await client.put(
            f"/api/v1/workspaces/{WS_ID}/nudges/{uuid.uuid4()}",
            json={"due_date": datetime.now(UTC).isoformat()},
        )
        assert response.status_code == 404

    async def test_update_due_date_returns_200(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """PUT /nudges/{id} updates the due date inline."""
        nudge = _make_mock_nudge_stub()
        mock_result = MagicMock()
        mock_result.unique.return_value.scalar_one_or_none.return_value = nudge
        mock_db.execute = AsyncMock(return_value=mock_result)

        new_due = datetime.now(UTC) + timedelta(days=3)
        response = await client.put(
            f"/api/v1/workspaces/{WS_ID}/nudges/{NUDGE_ID}",
            json={"due_date": new_due.isoformat()},
        )

        assert response.status_code == 200
        assert datetime.fromisoformat(response.json()["due_date"]) == new_due
        assert nudge.due_date == new_due
        mock_db.commit.assert_awaited_once()

    async def test_update_unassign_returns_200(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """Sending assigned_to_user_id=null explicitly unassigns the task."""
        nudge = _make_mock_nudge_stub()
        nudge.assigned_to_user_id = 5
        mock_result = MagicMock()
        mock_result.unique.return_value.scalar_one_or_none.return_value = nudge
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = await client.put(
            f"/api/v1/workspaces/{WS_ID}/nudges/{NUDGE_ID}",
            json={"assigned_to_user_id": None},
        )

        assert response.status_code == 200
        assert nudge.assigned_to_user_id is None
        mock_db.commit.assert_awaited_once()

    async def test_update_assignee_not_member_returns_422(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """Reassigning to a non-member fails closed with 422."""
        nudge = _make_mock_nudge_stub()
        nudge_result = MagicMock()
        nudge_result.unique.return_value.scalar_one_or_none.return_value = nudge
        mock_db.execute = AsyncMock(side_effect=[nudge_result, _result_returning(None)])

        response = await client.put(
            f"/api/v1/workspaces/{WS_ID}/nudges/{NUDGE_ID}",
            json={"assigned_to_user_id": 777},
        )
        assert response.status_code == 422


class TestListNudgesContactFilter:
    """contact_id query filter on GET /nudges."""

    async def test_contact_id_filter_accepted(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """GET /nudges?contact_id=7 → 200 with an empty page."""
        pagination_result = PaginationResult(items=[], total=0, page=1, page_size=20, pages=1)
        with patch("app.api.v1.nudges.paginate", new_callable=AsyncMock) as mock_paginate:
            mock_paginate.return_value = pagination_result
            response = await client.get(f"/api/v1/workspaces/{WS_ID}/nudges?contact_id=7")

        assert response.status_code == 200
        assert response.json()["total"] == 0

    async def test_contact_id_filter_invalid_returns_422(self, client: AsyncClient) -> None:
        """GET /nudges?contact_id=abc → 422."""
        response = await client.get(f"/api/v1/workspaces/{WS_ID}/nudges?contact_id=abc")
        assert response.status_code == 422


class TestNudgeSettingsAuth:
    """Auth + validation for /nudge-settings endpoints."""

    async def test_get_settings_without_auth_returns_401(self, noauth_client: AsyncClient) -> None:
        """GET /nudge-settings without auth returns 401."""
        response = await noauth_client.get(f"/api/v1/workspaces/{WS_ID}/nudge-settings")
        assert response.status_code == 401

    async def test_update_settings_without_auth_returns_401(
        self, noauth_client: AsyncClient
    ) -> None:
        """PUT /nudge-settings without auth returns 401."""
        response = await noauth_client.put(
            f"/api/v1/workspaces/{WS_ID}/nudge-settings",
            json={"enabled": False},
        )
        assert response.status_code == 401

    async def test_update_settings_lead_days_out_of_range_returns_422(
        self, client: AsyncClient
    ) -> None:
        """PUT /nudge-settings with lead_days=0 (violates ge=1) returns 422."""
        response = await client.put(
            f"/api/v1/workspaces/{WS_ID}/nudge-settings",
            json={"lead_days": 0},
        )
        assert response.status_code == 422

    async def test_update_settings_lead_days_too_high_returns_422(
        self, client: AsyncClient
    ) -> None:
        """PUT /nudge-settings with lead_days=31 (violates le=30) returns 422."""
        response = await client.put(
            f"/api/v1/workspaces/{WS_ID}/nudge-settings",
            json={"lead_days": 31},
        )
        assert response.status_code == 422

    async def test_update_settings_cooling_days_too_low_returns_422(
        self, client: AsyncClient
    ) -> None:
        """PUT /nudge-settings with cooling_days=6 (violates ge=7) returns 422."""
        response = await client.put(
            f"/api/v1/workspaces/{WS_ID}/nudge-settings",
            json={"cooling_days": 6},
        )
        assert response.status_code == 422

    async def test_update_settings_cooling_days_too_high_returns_422(
        self, client: AsyncClient
    ) -> None:
        """PUT /nudge-settings with cooling_days=400 (violates le=365) returns 422."""
        response = await client.put(
            f"/api/v1/workspaces/{WS_ID}/nudge-settings",
            json={"cooling_days": 400},
        )
        assert response.status_code == 422


class TestInvalidWorkspaceId:
    """Validate workspace_id path parameter is UUID (via real dependency)."""

    async def test_invalid_workspace_uuid_rejected(self, noauth_client: AsyncClient) -> None:
        """Non-UUID workspace_id is rejected (401 from auth or 422 from path).

        FastAPI runs dependencies in declaration order; the OAuth2 scheme may
        raise 401 before `get_workspace` validates the UUID. Either outcome
        is acceptable — the request never reaches the handler.
        """
        response = await noauth_client.get("/api/v1/workspaces/not-a-uuid/nudges")
        assert response.status_code in (401, 422)
