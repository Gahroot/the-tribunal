"""Billing status/checkout/portal contract tests (RF-007).

The Settings → Billing tab and the /billing page both render from
``GET /billing/status``. These tests pin the fields that let the UI show
honest state instead of dead controls: whether billing is configured, whether
checkout/portal can work, and that a Stripe lookup failure is an error rather
than a silent "not subscribed". DB- and Stripe-free via overrides/mocks.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
import stripe
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user
from app.api.v1 import billing as billing_module
from app.core.config import settings as app_settings
from app.core.encryption import encrypt_json
from app.db.session import get_db
from app.models.workspace import Workspace

WS_ID = uuid.uuid4()


@asynccontextmanager
async def _test_lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


def _membership_db(memberships: list[SimpleNamespace]) -> AsyncMock:
    """Local query fixture retaining membership filters and default selection."""
    db = AsyncMock()

    async def execute(stmt: Any) -> MagicMock:
        params = stmt.compile().params
        result = MagicMock()
        if stmt.column_descriptions[0]["entity"] is Workspace:
            result.scalar_one_or_none.return_value = SimpleNamespace(
                id=params["id_1"], name="Brand A", is_active=True
            )
            return result

        rows = [m for m in memberships if m.user_id == params["user_id_1"]]
        if "workspace_id_1" in params:
            rows = [m for m in rows if m.workspace_id == params["workspace_id_1"]]
        if "is_default IS true" in str(stmt):
            rows = [m for m in rows if m.is_default]
        if stmt._order_by_clauses:
            rows.sort(key=lambda m: m.created_at)
        if stmt._limit_clause is not None:
            rows = rows[:1]
        result.scalar_one_or_none.return_value = rows[0] if rows else None
        return result

    db.execute.side_effect = execute
    return db


def _membership(
    workspace_id: uuid.UUID = WS_ID,
    role: str = "owner",
    *,
    is_default: bool = True,
    created_at: int = 0,
    user_id: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        workspace_id=workspace_id,
        role=role,
        user_id=user_id,
        is_default=is_default,
        created_at=created_at,
    )


def _app(db: AsyncMock | None = None, api_key_workspace_id: uuid.UUID | None = None) -> FastAPI:
    app = FastAPI(lifespan=_test_lifespan)
    test_db = db if db is not None else _membership_db([_membership()])

    if api_key_workspace_id is not None:

        @app.middleware("http")
        async def bind_api_key(request: Request, call_next: Any) -> Any:
            request.state.api_key_workspace_id = api_key_workspace_id
            return await call_next(request)

    async def override_get_db() -> AsyncIterator[AsyncMock]:
        yield test_db

    async def override_get_current_user() -> SimpleNamespace:
        return SimpleNamespace(id=1, is_active=True, email="owner@example.test")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.include_router(billing_module.router, prefix="/api/v1/billing")
    return app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def stripe_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Configure fake Stripe settings and stub workspace/customer lookups."""
    state: dict[str, Any] = {"customer_id": None, "client": MagicMock()}
    monkeypatch.setattr(app_settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(app_settings, "stripe_price_id", "price_test_fake")
    monkeypatch.setattr(app_settings, "frontend_url", "https://app.example.test")

    def integration_for_workspace(_workspace_id: uuid.UUID, _db: Any) -> Any:
        if state["customer_id"] is None:
            return None
        return SimpleNamespace(
            encrypted_credentials=encrypt_json({"customer_id": state["customer_id"]})
        )

    monkeypatch.setattr(
        billing_module, "_get_stripe_integration", AsyncMock(side_effect=integration_for_workspace)
    )
    state["client_factory"] = MagicMock(return_value=state["client"])
    monkeypatch.setattr(billing_module, "_stripe_client", state["client_factory"])
    return state


async def test_status_reports_unconfigured_billing(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_settings, "stripe_secret_key", "")
    resp = await client.get(f"/api/v1/billing/status?billing_account_id={WS_ID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["subscribed"] is False
    assert body["configured"] is False
    assert body["checkout_available"] is False
    assert body["portal_available"] is False


async def test_status_without_customer_offers_checkout_only(
    client: AsyncClient, stripe_env: dict[str, Any]
) -> None:
    resp = await client.get(f"/api/v1/billing/status?billing_account_id={WS_ID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "billing_account": {"id": str(WS_ID), "name": "Brand A", "kind": "workspace"},
        "subscribed": False,
        "plan": None,
        "status": None,
        "current_period_end": None,
        "configured": True,
        "checkout_available": True,
        "portal_available": False,
    }


async def test_status_without_price_disables_checkout(
    client: AsyncClient, stripe_env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_settings, "stripe_price_id", "")
    body = (await client.get(f"/api/v1/billing/status?billing_account_id={WS_ID}")).json()
    assert body["configured"] is True
    assert body["checkout_available"] is False


async def test_status_active_subscription(client: AsyncClient, stripe_env: dict[str, Any]) -> None:
    stripe_env["customer_id"] = "cus_test"
    price = SimpleNamespace(nickname="Realtor Monthly", product="prod_x")
    sub = SimpleNamespace(
        status="active",
        trial_end=None,
        items=SimpleNamespace(data=[SimpleNamespace(price=price)]),
    )
    stripe_env["client"].subscriptions.list.return_value = SimpleNamespace(data=[sub])

    body = (await client.get(f"/api/v1/billing/status?billing_account_id={WS_ID}")).json()
    assert body["subscribed"] is True
    assert body["plan"] == "Realtor Monthly"
    assert body["status"] == "active"
    assert body["portal_available"] is True


async def test_status_stripe_failure_is_an_error_not_unsubscribed(
    client: AsyncClient, stripe_env: dict[str, Any]
) -> None:
    stripe_env["customer_id"] = "cus_test"
    connection_error = cast(Any, stripe.APIConnectionError)("down")
    stripe_env["client"].subscriptions.list.side_effect = connection_error

    resp = await client.get(f"/api/v1/billing/status?billing_account_id={WS_ID}")
    assert resp.status_code == 502
    assert "sk_test_fake" not in resp.text


async def test_workspace_lookup_tolerates_multiple_default_memberships() -> None:
    """A user with several ``is_default`` memberships must not 500 billing."""
    ws_id = uuid.uuid4()
    db = _membership_db(
        [
            _membership(ws_id),
            _membership(uuid.uuid4(), role="member", created_at=1),
        ]
    )

    resolved = await billing_module._get_user_workspace_id(
        cast(Any, SimpleNamespace(id=1)),
        db,
        Request({"type": "http"}),
    )

    assert resolved == ws_id
    stmt = db.execute.call_args_list[0].args[0]
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "ORDER BY workspace_memberships.created_at ASC" in sql
    assert "LIMIT 1" in sql


async def test_checkout_and_portal_return_to_billing_page(
    client: AsyncClient, stripe_env: dict[str, Any]
) -> None:
    stripe_client = stripe_env["client"]
    stripe_client.checkout.sessions.create.return_value = SimpleNamespace(
        id="cs_test", url="https://checkout.stripe.test/cs_test"
    )
    resp = await client.post("/api/v1/billing/checkout", json={"billing_account_id": str(WS_ID)})
    assert resp.status_code == 200
    params = stripe_client.checkout.sessions.create.call_args.kwargs["params"]
    assert (
        params["success_url"]
        == f"https://app.example.test/billing?billing_account_id={WS_ID}&checkout=success"
    )
    assert (
        params["cancel_url"]
        == f"https://app.example.test/billing?billing_account_id={WS_ID}&checkout=canceled"
    )
    assert params["metadata"] == {"workspace_id": str(WS_ID)}

    stripe_env["customer_id"] = "cus_test"
    stripe_client.billing_portal.sessions.create.return_value = SimpleNamespace(
        url="https://billing.stripe.test/p"
    )
    resp = await client.post(f"/api/v1/billing/portal?billing_account_id={WS_ID}")
    assert resp.status_code == 200
    assert resp.json() == {"portal_url": "https://billing.stripe.test/p"}
    portal_params = stripe_client.billing_portal.sessions.create.call_args.kwargs["params"]
    assert (
        portal_params["return_url"]
        == f"https://app.example.test/billing?billing_account_id={WS_ID}"
    )
    assert portal_params["customer"] == "cus_test"


async def _billing_request(client: AsyncClient, endpoint: str) -> Any:
    url = f"/api/v1/billing/{endpoint}"
    if endpoint in ("status", "portal"):
        url += f"?billing_account_id={WS_ID}"
    if endpoint == "status":
        return await client.get(url)
    return await client.post(
        url, json={"billing_account_id": str(WS_ID)} if endpoint == "checkout" else None
    )


@pytest.mark.parametrize("endpoint", ["checkout", "portal", "status"])
@pytest.mark.parametrize("role", ["member", "billing_manager", "unknown"])
async def test_billing_denies_unapproved_roles_before_customer_or_provider_lookup(
    endpoint: str, role: str, stripe_env: dict[str, Any]
) -> None:
    db = _membership_db([_membership(role=role)])
    async with AsyncClient(
        transport=ASGITransport(app=_app(db)), base_url="http://testserver"
    ) as ac:
        response = await _billing_request(ac, endpoint)

    assert response.status_code == 403
    billing_module._get_stripe_integration.assert_not_awaited()
    stripe_env["client_factory"].assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("endpoint", ["checkout", "portal", "status"])
@pytest.mark.parametrize(
    ("role", "has_default", "expected"),
    [
        ("member", True, 403),
        ("member", False, 403),
        ("owner", True, 200),
        ("admin", True, 200),
        ("owner", False, 200),
        ("admin", False, 200),
    ],
)
async def test_billing_uses_authority_and_customer_of_the_same_selected_workspace(
    endpoint: str,
    role: str,
    has_default: bool,
    expected: int,
    stripe_env: dict[str, Any],
) -> None:
    """A privileged role elsewhere must neither authorize nor redirect billing."""
    other_id = uuid.uuid4()
    db = _membership_db(
        [
            _membership(role=role, is_default=has_default),
            _membership(
                other_id,
                role="owner" if role == "member" else "member",
                is_default=False,
                created_at=1,
            ),
            _membership(WS_ID, role="owner", user_id=2),
        ]
    )
    stripe_env["customer_id"] = "cus_selected_workspace"
    provider = stripe_env["client"]
    provider.checkout.sessions.create.return_value = SimpleNamespace(
        id="cs_fixture", url="https://checkout.stripe.test/fixture"
    )
    provider.billing_portal.sessions.create.return_value = SimpleNamespace(
        url="https://billing.stripe.test/fixture"
    )
    provider.subscriptions.list.return_value = SimpleNamespace(data=[])

    async with AsyncClient(
        transport=ASGITransport(app=_app(db)), base_url="http://testserver"
    ) as ac:
        response = await _billing_request(ac, endpoint)

    assert response.status_code == expected
    if expected == 403:
        billing_module._get_stripe_integration.assert_not_awaited()
        stripe_env["client_factory"].assert_not_called()
        return

    billing_module._get_stripe_integration.assert_awaited_once_with(WS_ID, db)
    calls = {
        "checkout": provider.checkout.sessions.create,
        "portal": provider.billing_portal.sessions.create,
        "status": provider.subscriptions.list,
    }
    params = calls[endpoint].call_args.kwargs["params"]
    assert params["customer"] == "cus_selected_workspace"
    if endpoint == "checkout":
        assert params["metadata"] == {"workspace_id": str(WS_ID)}
        assert "customer_email" not in params
        assert response.json() == {"checkout_url": "https://checkout.stripe.test/fixture"}
    elif endpoint == "portal":
        assert response.json() == {"portal_url": "https://billing.stripe.test/fixture"}
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("endpoint", ["checkout", "portal", "status"])
async def test_billing_rejects_api_key_bound_to_another_workspace(
    endpoint: str, stripe_env: dict[str, Any]
) -> None:
    app = _app(api_key_workspace_id=uuid.uuid4())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        response = await _billing_request(ac, endpoint)

    assert response.status_code == 403
    billing_module._get_stripe_integration.assert_not_awaited()
    stripe_env["client_factory"].assert_not_called()


@pytest.mark.parametrize("endpoint", ["checkout", "portal", "status"])
async def test_billing_member_denied_even_when_provider_unconfigured(
    endpoint: str, stripe_env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_settings, "stripe_secret_key", "")
    db = _membership_db([_membership(role="member")])
    async with AsyncClient(
        transport=ASGITransport(app=_app(db)), base_url="http://testserver"
    ) as ac:
        response = await _billing_request(ac, endpoint)

    assert response.status_code == 403
    billing_module._get_stripe_integration.assert_not_awaited()
    stripe_env["client_factory"].assert_not_called()


@pytest.mark.parametrize("default_b", [False, True])
async def test_explicit_account_survives_default_and_active_brand_changes(
    default_b: bool, stripe_env: dict[str, Any]
) -> None:
    brand_b = uuid.uuid4()
    db = _membership_db(
        [
            _membership(is_default=not default_b),
            _membership(brand_b, role="admin", is_default=default_b, created_at=1),
        ]
    )
    stripe_env["customer_id"] = "cus_original_a"
    provider = stripe_env["client"]
    provider.subscriptions.list.return_value = SimpleNamespace(data=[])
    provider.billing_portal.sessions.create.return_value = SimpleNamespace(
        url="https://billing.stripe.test/a"
    )
    provider.checkout.sessions.create.return_value = SimpleNamespace(
        id="cs_a", url="https://checkout.stripe.test/a"
    )
    async with AsyncClient(
        transport=ASGITransport(app=_app(db)), base_url="http://testserver"
    ) as ac:
        account = await ac.get("/api/v1/billing/account")
        assert account.json()["id"] == str(brand_b if default_b else WS_ID)
        # A captured account remains A even with B selected/default. Sidebar
        # context is not billing authority and must not override the target.
        pinned = await ac.get(
            f"/api/v1/billing/account?billing_account_id={WS_ID}",
            headers={"X-Workspace-ID": str(brand_b)},
        )
        assert pinned.json()["id"] == str(WS_ID)
        for endpoint in ("status", "portal", "checkout"):
            response = await _billing_request(ac, endpoint)
            assert response.status_code == 200
            if endpoint == "status":
                assert response.json()["billing_account"]["id"] == str(WS_ID)
    for call in billing_module._get_stripe_integration.await_args_list:
        assert call.args == (WS_ID, db)
    for operation in (
        provider.subscriptions.list,
        provider.billing_portal.sessions.create,
        provider.checkout.sessions.create,
    ):
        assert operation.call_args.kwargs["params"]["customer"] == "cus_original_a"
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("endpoint", ["account", "status", "portal", "checkout"])
@pytest.mark.parametrize("failure", ["missing", "inactive", "member"])
async def test_explicit_account_fails_closed_without_fallback(
    endpoint: str, failure: str, stripe_env: dict[str, Any]
) -> None:
    db = _membership_db(
        [
            *(
                []
                if failure == "missing"
                else [_membership(role="member" if failure == "member" else "owner")]
            ),
            _membership(uuid.uuid4(), role="owner", created_at=1),
        ]
    )
    original_execute = db.execute.side_effect

    async def execute(stmt: Any) -> MagicMock:
        result = await original_execute(stmt)
        if failure == "inactive" and stmt.column_descriptions[0]["entity"] is Workspace:
            result.scalar_one_or_none.return_value.is_active = False
        return result

    db.execute.side_effect = execute
    async with AsyncClient(
        transport=ASGITransport(app=_app(db)), base_url="http://testserver"
    ) as ac:
        response = (
            await ac.get(f"/api/v1/billing/account?billing_account_id={WS_ID}")
            if endpoint == "account"
            else await _billing_request(ac, endpoint)
        )
    assert response.status_code == (403 if failure == "member" else 404)
    billing_module._get_stripe_integration.assert_not_awaited()
    stripe_env["client_factory"].assert_not_called()


@pytest.mark.parametrize("endpoint", ["status", "portal", "checkout"])
async def test_billing_operations_require_explicit_account(
    endpoint: str, stripe_env: dict[str, Any]
) -> None:
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://testserver") as ac:
        response = (
            await ac.get(f"/api/v1/billing/{endpoint}")
            if endpoint == "status"
            else await ac.post(f"/api/v1/billing/{endpoint}", json={})
        )
    assert response.status_code == 422
    stripe_env["client_factory"].assert_not_called()


async def test_discovery_does_not_replace_member_default_with_owned_brand(
    stripe_env: dict[str, Any],
) -> None:
    db = _membership_db(
        [
            _membership(role="member"),
            _membership(uuid.uuid4(), role="owner", is_default=False, created_at=1),
        ]
    )
    async with AsyncClient(
        transport=ASGITransport(app=_app(db)), base_url="http://testserver"
    ) as ac:
        response = await ac.get("/api/v1/billing/account")
    assert response.status_code == 403
    stripe_env["client_factory"].assert_not_called()
