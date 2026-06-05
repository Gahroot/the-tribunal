"""Auth + routing tests for the Reviews & Reputation engine endpoints.

Focuses on the public rating-gate routing contract (the negative-feedback
firewall) and authenticated-route auth, using FastAPI dependency overrides and a
stubbed ReviewService so the tests stay DB-free. The full DB-backed flow is
verified by live endpoint probes recorded on the goal run.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db, get_workspace
from app.api.v1 import reviews as reviews_module
from app.schemas.review import (
    PublicFeedbackResult,
    PublicRatingResult,
    PublicReviewRequest,
    ReviewRequestStatusSchema,
)

WS_ID = uuid.uuid4()


@asynccontextmanager
async def _test_lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


def _make_mock_workspace() -> MagicMock:
    ws = MagicMock()
    ws.id = WS_ID
    ws.is_active = True
    ws.name = "QA Co"
    ws.settings = {"review_settings": {"enabled": True}}
    return ws


def _make_mock_user() -> MagicMock:
    user = MagicMock()
    user.id = 1
    user.is_active = True
    user.email = "tester@example.com"
    return user


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

    app.include_router(
        reviews_module.router,
        prefix="/api/v1/workspaces/{workspace_id}/reviews",
    )
    app.include_router(reviews_module.public_router, prefix="/api/v1/p/reviews")
    return app


def _public_app(mock_db: AsyncMock) -> FastAPI:
    app = FastAPI(lifespan=_test_lifespan)

    async def override_get_db() -> AsyncIterator[AsyncMock]:
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    app.include_router(reviews_module.public_router, prefix="/api/v1/p/reviews")
    # Include authed router too (no auth override) to assert 401 behavior.
    app.include_router(
        reviews_module.router,
        prefix="/api/v1/workspaces/{workspace_id}/reviews",
    )
    return app


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
async def auth_client(mock_db: AsyncMock) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=_auth_app(mock_db)),
        base_url="http://testserver",
    ) as ac:
        yield ac


@pytest.fixture
async def public_client(mock_db: AsyncMock) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=_public_app(mock_db)),
        base_url="http://testserver",
    ) as ac:
        yield ac


class TestAuth:
    async def test_list_reviews_without_auth_returns_401(self, public_client: AsyncClient) -> None:
        resp = await public_client.get(f"/api/v1/workspaces/{WS_ID}/reviews")
        assert resp.status_code == 401

    async def test_settings_without_auth_returns_401(self, public_client: AsyncClient) -> None:
        resp = await public_client.get(f"/api/v1/workspaces/{WS_ID}/reviews/settings")
        assert resp.status_code == 401


class TestPublicRatingGate:
    """The rating gate: high → public URL, low → private feedback form."""

    async def test_high_rating_routes_to_public_url(
        self, public_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_submit(self: object, token: str, rating: int) -> PublicRatingResult:
            return PublicRatingResult(
                success=True,
                rating=rating,
                is_positive=True,
                redirect_url="https://g.page/r/qa",
                show_feedback_form=False,
                message="Thanks!",
            )

        monkeypatch.setattr(
            reviews_module.ReviewService, "submit_rating", fake_submit, raising=True
        )
        resp = await public_client.post("/api/v1/p/reviews/sometoken/rate", json={"rating": 5})
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_positive"] is True
        assert body["redirect_url"] == "https://g.page/r/qa"
        assert body["show_feedback_form"] is False

    async def test_low_rating_shows_feedback_form_no_redirect(
        self, public_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_submit(self: object, token: str, rating: int) -> PublicRatingResult:
            return PublicRatingResult(
                success=True,
                rating=rating,
                is_positive=False,
                redirect_url=None,
                show_feedback_form=True,
                message="Tell us more.",
            )

        monkeypatch.setattr(
            reviews_module.ReviewService, "submit_rating", fake_submit, raising=True
        )
        resp = await public_client.post("/api/v1/p/reviews/sometoken/rate", json={"rating": 2})
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_positive"] is False
        assert body["redirect_url"] is None
        assert body["show_feedback_form"] is True

    async def test_rating_out_of_range_returns_422(self, public_client: AsyncClient) -> None:
        resp = await public_client.post("/api/v1/p/reviews/sometoken/rate", json={"rating": 6})
        assert resp.status_code == 422

    async def test_get_public_request(
        self, public_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_get(self: object, token: str) -> PublicReviewRequest:
            return PublicReviewRequest(
                token=token,
                status=ReviewRequestStatusSchema.SENT,
                rating=None,
                business_name="QA Co",
                contact_first_name="Dana",
                positive_threshold=4,
                already_submitted=False,
            )

        monkeypatch.setattr(
            reviews_module.ReviewService, "get_public_request", fake_get, raising=True
        )
        resp = await public_client.get("/api/v1/p/reviews/abc")
        assert resp.status_code == 200
        assert resp.json()["business_name"] == "QA Co"

    async def test_submit_feedback(
        self, public_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_feedback(
            self: object, token: str, body: str, reviewer_name: str | None
        ) -> None:
            return None

        monkeypatch.setattr(
            reviews_module.ReviewService, "submit_feedback", fake_feedback, raising=True
        )
        resp = await public_client.post(
            "/api/v1/p/reviews/abc/feedback",
            json={"body": "Slow service", "reviewer_name": "Dana"},
        )
        assert resp.status_code == 200
        assert (
            resp.json()
            == PublicFeedbackResult(
                success=True, message="Thank you for your feedback. We'll be in touch."
            ).model_dump()
        )

    async def test_submit_feedback_empty_body_returns_422(self, public_client: AsyncClient) -> None:
        resp = await public_client.post("/api/v1/p/reviews/abc/feedback", json={"body": ""})
        assert resp.status_code == 422
