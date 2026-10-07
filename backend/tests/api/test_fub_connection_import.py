"""Follow Up Boss connect → save → import regressions (finding RF-008).

The real ``get_workspace``/``get_workspace_admin`` dependencies, credential
storage (Fernet), lookup hashing and import/dedupe logic run against a small
in-memory session fake; only Follow Up Boss HTTP and the drip bootstrap are
stubbed. No real CRM data or credentials are used.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError

from app.api.deps import get_current_user, get_db
from app.api.v1.integrations import followupboss as fub_module
from app.models.contact import Contact
from app.models.workspace import Workspace, WorkspaceIntegration, WorkspaceMembership

USER_ID = 7
DEFAULT_WS = uuid.uuid4()  # the user's other/default workspace
SELECTED_WS = uuid.uuid4()  # the workspace explicitly chosen in the wizard
FOREIGN_WS = uuid.uuid4()  # not a member

GOOD_KEY = "fub_test_good_key_0001"
OLD_KEY = "fub_test_old_key_0002"
BAD_KEY = "fub_test_bad_key_0003"

FUB_PEOPLE = [
    {
        "id": 101,
        "firstName": "Ava",
        "lastName": "Stone",
        "phones": [{"value": "(415) 555-0101"}],
        "emails": [{"value": "ava@example.test"}],
    },
    {"id": 102, "firstName": "Ben", "phones": [{"value": "+14155550102"}], "emails": []},
    {"id": 103, "firstName": "Cy", "phones": [], "emails": [{"value": "cy@example.test"}]},
]


@asynccontextmanager
async def _noop_lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


def _result(value: object | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _params(statement: Any) -> dict[str, Any]:
    return dict(statement.compile().params)


class FakeSession:
    """Just enough AsyncSession for these routes, keyed by workspace."""

    def __init__(self, member_of: dict[uuid.UUID, str]) -> None:
        self.member_of = member_of
        self.integrations: dict[uuid.UUID, WorkspaceIntegration] = {}
        self.contacts: list[Contact] = []
        self._pending: list[Any] = []
        self._ws_lookup: list[uuid.UUID] = []
        self._next_id = 1
        self.commit = AsyncMock(side_effect=self._commit)
        self.rollback = AsyncMock(side_effect=self._rollback)

    async def execute(self, statement: Any) -> MagicMock:
        sql = str(statement.compile()).lower()
        params = _params(statement)
        ws_ids = [v for v in params.values() if isinstance(v, uuid.UUID)]
        if "from workspace_memberships" in sql:
            ws_id = ws_ids[0]
            role = self.member_of.get(ws_id)
            if role is None:
                return _result(None)
            self._ws_lookup.append(ws_id)
            return _result(
                WorkspaceMembership(id=uuid.uuid4(), user_id=USER_ID, workspace_id=ws_id, role=role)
            )
        if "from workspaces" in sql:
            ws_id = self._ws_lookup.pop()
            return _result(Workspace(id=ws_id, name="WS", slug=ws_id.hex[:8], is_active=True))
        if "from workspace_integrations" in sql:
            integration = self.integrations.get(ws_ids[0])
            pending = [
                p
                for p in self._pending
                if isinstance(p, WorkspaceIntegration) and p.workspace_id == ws_ids[0]
            ]
            if integration is None and pending:
                integration = pending[0]
            if integration is not None and "is_active" in sql and not integration.is_active:
                integration = None
            return _result(integration)
        if "from contacts" in sql:
            wanted = {v for v in params.values() if isinstance(v, str)}
            for c in self.contacts:
                if c.workspace_id == ws_ids[0] and wanted & {
                    c.source,
                    c.phone_hash,
                    c.email_hash,
                }:
                    return _result(c.id)
            return _result(None)
        raise AssertionError(f"unexpected query: {sql}")

    def add(self, obj: Any) -> None:
        self._pending.append(obj)

    async def flush(self) -> None:
        for obj in self._pending:
            if isinstance(obj, Contact) and obj not in self.contacts:
                obj.id = self._next_id
                self._next_id += 1
                self.contacts.append(obj)

    def begin_nested(self) -> Any:
        @asynccontextmanager
        async def _sp() -> AsyncIterator[None]:
            yield

        return _sp()

    async def _commit(self) -> None:
        for obj in self._pending:
            if isinstance(obj, WorkspaceIntegration):
                self.integrations[obj.workspace_id] = obj
        self._pending.clear()

    async def _rollback(self) -> None:
        self._pending.clear()


class FakeFUB:
    """Stand-in for FollowUpBossClient keyed on the API key it was built with."""

    instances: list[FakeFUB] = []
    transient = False

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        FakeFUB.instances.append(self)

    def _check(self) -> None:
        request = httpx.Request("GET", "https://fub.invalid/v1/me")
        if FakeFUB.transient:
            raise httpx.ConnectError("down", request=request)
        if self.api_key not in (GOOD_KEY, OLD_KEY):
            raise httpx.HTTPStatusError(
                "401", request=request, response=httpx.Response(401, request=request)
            )

    async def verify(self) -> dict[str, Any]:
        self._check()
        return {"name": "Test Agent", "email": "agent@example.test"}

    async def get_people(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        self._check()
        return {"people": FUB_PEOPLE[offset : offset + limit], "_metadata": {"total": 3}}

    async def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def fake_fub(monkeypatch: pytest.MonkeyPatch) -> type[FakeFUB]:
    FakeFUB.instances = []
    FakeFUB.transient = False
    monkeypatch.setattr(fub_module, "FollowUpBossClient", FakeFUB)
    monkeypatch.setattr(fub_module, "auto_create_drip_for_imports", AsyncMock())
    return FakeFUB


def _app(db: FakeSession) -> FastAPI:
    app = FastAPI(lifespan=_noop_lifespan)

    async def override_get_db() -> AsyncIterator[FakeSession]:
        yield db

    user = MagicMock()
    user.id = USER_ID
    user.is_active = True
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    app.include_router(
        fub_module.workspace_router, prefix="/api/v1/workspaces/{workspace_id}/realtor"
    )
    return app


def _client(db: FakeSession) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=_app(db)), base_url="http://test")


def _url(ws: uuid.UUID, path: str) -> str:
    return f"/api/v1/workspaces/{ws}/realtor/{path}"


def _saved_key(db: FakeSession, ws: uuid.UUID) -> str:
    return str(db.integrations[ws].credentials["api_key"])


async def test_verify_save_import_lands_in_selected_workspace() -> None:
    db = FakeSession({DEFAULT_WS: "owner", SELECTED_WS: "owner"})
    async with _client(db) as client:
        before = await client.get(_url(SELECTED_WS, "fub-connection"))
        connect = await client.put(_url(SELECTED_WS, "fub-connection"), json={"api_key": GOOD_KEY})
        status_after = await client.get(_url(SELECTED_WS, "fub-connection"))
        imported = await client.post(
            _url(SELECTED_WS, "import-fub-contacts"), json={"import_all": True}
        )
        default_import = await client.post(
            _url(DEFAULT_WS, "import-fub-contacts"), json={"import_all": True}
        )

    assert before.json() == {"connected": False, "account_name": None}
    assert connect.status_code == 200, connect.text
    assert connect.json() == {"connected": True, "account_name": "Test Agent"}
    # Readiness survives a reload: it's read back from the stored integration.
    assert status_after.json() == {"connected": True, "account_name": "Test Agent"}

    # Saved encrypted on the selected workspace only — never on the default.
    assert set(db.integrations) == {SELECTED_WS}
    assert GOOD_KEY not in db.integrations[SELECTED_WS].encrypted_credentials
    assert _saved_key(db, SELECTED_WS) == GOOD_KEY

    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert (body["imported"], body["skipped"], body["failed"]) == (2, 0, 1)
    assert body["failures"] == [{"fub_id": 103, "reason": "missing_phone"}]
    assert {c.workspace_id for c in db.contacts} == {SELECTED_WS}
    assert {c.phone_number for c in db.contacts} == {"+14155550101", "+14155550102"}

    # The default workspace has no connection, so nothing leaks into it.
    assert default_import.status_code == 404
    for resp in (connect, status_after, imported):
        assert GOOD_KEY not in resp.text


async def test_repeat_import_skips_existing_contacts() -> None:
    db = FakeSession({SELECTED_WS: "owner"})
    async with _client(db) as client:
        await client.put(_url(SELECTED_WS, "fub-connection"), json={"api_key": GOOD_KEY})
        first = await client.post(
            _url(SELECTED_WS, "import-fub-contacts"), json={"import_all": True}
        )
        second = await client.post(
            _url(SELECTED_WS, "import-fub-contacts"), json={"import_all": True}
        )

    assert first.json()["imported"] == 2
    assert (second.json()["imported"], second.json()["skipped"]) == (0, 2)
    assert len(db.contacts) == 2


async def test_save_failure_is_not_reported_connected() -> None:
    db = FakeSession({SELECTED_WS: "owner"})
    db.commit.side_effect = OperationalError("commit", {}, Exception("db down"))
    async with _client(db) as client:
        resp = await client.put(_url(SELECTED_WS, "fub-connection"), json={"api_key": GOOD_KEY})
        db.commit.side_effect = db._commit
        status_after = await client.get(_url(SELECTED_WS, "fub-connection"))

    assert resp.status_code == 503
    assert "connected" not in resp.json()
    db.rollback.assert_awaited()
    assert status_after.json()["connected"] is False
    assert GOOD_KEY not in resp.text


async def test_missing_workspace_saves_nothing_and_never_calls_fub() -> None:
    db = FakeSession({SELECTED_WS: "owner"})
    async with _client(db) as client:
        resp = await client.put(_url(FOREIGN_WS, "fub-connection"), json={"api_key": GOOD_KEY})

    assert resp.status_code == 404
    assert FakeFUB.instances == []
    assert db.integrations == {}
    db.commit.assert_not_awaited()


@pytest.mark.parametrize(
    ("key", "transient", "expected_status"),
    [(BAD_KEY, False, 422), (GOOD_KEY, True, 502)],
)
async def test_failed_check_preserves_existing_connection(
    key: str, transient: bool, expected_status: int
) -> None:
    db = FakeSession({SELECTED_WS: "owner"})
    async with _client(db) as client:
        await client.put(_url(SELECTED_WS, "fub-connection"), json={"api_key": OLD_KEY})
        db.commit.reset_mock()
        FakeFUB.transient = transient
        resp = await client.put(_url(SELECTED_WS, "fub-connection"), json={"api_key": key})
        status_after = await client.get(_url(SELECTED_WS, "fub-connection"))

    assert resp.status_code == expected_status
    db.commit.assert_not_awaited()
    assert _saved_key(db, SELECTED_WS) == OLD_KEY
    assert status_after.json()["connected"] is True
    assert key not in resp.text


async def test_import_with_rejected_stored_key_keeps_connection() -> None:
    db = FakeSession({SELECTED_WS: "owner"})
    async with _client(db) as client:
        await client.put(_url(SELECTED_WS, "fub-connection"), json={"api_key": GOOD_KEY})
        FakeFUB.transient = True
        resp = await client.post(
            _url(SELECTED_WS, "import-fub-contacts"), json={"import_all": True}
        )

    assert resp.status_code == 502
    assert db.contacts == []
    assert db.integrations[SELECTED_WS].is_active is True
