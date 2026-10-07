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
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user
from app.api.v1 import billing as billing_module
from app.core.config import settings as app_settings
from app.db.session import get_db

WS_ID = uuid.uuid4()


@asynccontextmanager
async def _test_lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


def _app() -> FastAPI:
    app = FastAPI(lifespan=_test_lifespan)

    async def override_get_db() -> AsyncIterator[AsyncMock]:
        yield AsyncMock()

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
    monkeypatch.setattr(billing_module, "_get_user_workspace_id", AsyncMock(return_value=WS_ID))
    monkeypatch.setattr(billing_module, "_get_stripe_integration", AsyncMock(return_value=None))
    monkeypatch.setattr(billing_module, "_get_customer_id", lambda _i: state["customer_id"])
    monkeypatch.setattr(billing_module, "_stripe_client", lambda: state["client"])
    return state


async def test_status_reports_unconfigured_billing(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_settings, "stripe_secret_key", "")
    resp = await client.get("/api/v1/billing/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["subscribed"] is False
    assert body["configured"] is False
    assert body["checkout_available"] is False
    assert body["portal_available"] is False


async def test_status_without_customer_offers_checkout_only(
    client: AsyncClient, stripe_env: dict[str, Any]
) -> None:
    resp = await client.get("/api/v1/billing/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
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
    body = (await client.get("/api/v1/billing/status")).json()
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

    body = (await client.get("/api/v1/billing/status")).json()
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

    resp = await client.get("/api/v1/billing/status")
    assert resp.status_code == 502
    assert "sk_test_fake" not in resp.text


async def test_workspace_lookup_tolerates_multiple_default_memberships() -> None:
    """A user with several ``is_default`` memberships must not 500 billing."""
    ws_id = uuid.uuid4()
    result = MagicMock()
    result.scalar_one_or_none.return_value = SimpleNamespace(workspace_id=ws_id)
    db = AsyncMock()
    db.execute.return_value = result

    resolved = await billing_module._get_user_workspace_id(
        cast(Any, SimpleNamespace(id=1)),
        db,
    )

    assert resolved == ws_id
    stmt = db.execute.call_args.args[0]
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
    resp = await client.post("/api/v1/billing/checkout", json={})
    assert resp.status_code == 200
    params = stripe_client.checkout.sessions.create.call_args.kwargs["params"]
    assert params["success_url"] == "https://app.example.test/billing?checkout=success"
    assert params["cancel_url"] == "https://app.example.test/billing?checkout=canceled"
    assert params["metadata"] == {"workspace_id": str(WS_ID)}

    stripe_env["customer_id"] = "cus_test"
    stripe_client.billing_portal.sessions.create.return_value = SimpleNamespace(
        url="https://billing.stripe.test/p"
    )
    resp = await client.post("/api/v1/billing/portal")
    assert resp.status_code == 200
    assert resp.json() == {"portal_url": "https://billing.stripe.test/p"}
    portal_params = stripe_client.billing_portal.sessions.create.call_args.kwargs["params"]
    assert portal_params["return_url"] == "https://app.example.test/billing"
