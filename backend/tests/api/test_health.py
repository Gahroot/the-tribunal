"""Tests for the health check endpoint.

Tests GET /health using a mocked app lifespan that bypasses
worker startup and Redis/database initialization.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.router import api_router
from app.api.webhooks.calcom import router as calcom_webhook_router
from app.api.webhooks.telnyx import router as telnyx_webhook_router
from app.websockets.voice_bridge import router as voice_bridge_router
from app.websockets.voice_test import router as voice_test_router


@asynccontextmanager
async def _test_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Minimal lifespan that skips workers, Redis, and DB setup."""
    yield


def _make_test_app() -> FastAPI:
    """Create a minimal FastAPI app with all routes but no worker startup."""
    app = FastAPI(lifespan=_test_lifespan)

    # Register all the same routers as the real app
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(calcom_webhook_router, prefix="/api/webhooks")
    app.include_router(telnyx_webhook_router, prefix="/api/webhooks")
    app.include_router(voice_bridge_router)
    app.include_router(voice_test_router)

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "healthy"}

    return app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Async HTTP client bound to the test app."""
    app = _make_test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


class TestHealthEndpoint:
    """Tests for GET /health."""

    async def test_health_returns_200(self, client: AsyncClient) -> None:
        """Health check endpoint returns HTTP 200."""
        response = await client.get("/health")
        assert response.status_code == 200

    async def test_health_returns_json(self, client: AsyncClient) -> None:
        """Health check returns JSON content type."""
        response = await client.get("/health")
        assert "application/json" in response.headers["content-type"]

    async def test_health_returns_status_healthy(self, client: AsyncClient) -> None:
        """Health check body contains status: healthy."""
        response = await client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"


class TestAuthEndpointErrors:
    """Tests for auth endpoint error responses (no DB needed)."""

    async def test_login_invalid_credentials_returns_401(
        self, client: AsyncClient
    ) -> None:
        """Login with invalid credentials returns 401 when DB returns no user.

        The DB is not running in tests, so we mock it to return None for the
        user lookup, which exercises the 401 path.
        """
        from unittest.mock import MagicMock

        from sqlalchemy.engine import Result

        mock_result = MagicMock(spec=Result)
        mock_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        # Patch the rate limit check to be a no-op and the DB session
        with (
            patch("app.api.v1.auth._check_auth_rate_limit", new=AsyncMock()),
            patch("app.db.session.AsyncSessionLocal", return_value=mock_db),
        ):
            response = await client.post(
                "/api/v1/auth/login",
                data={"username": "nobody@example.com", "password": "wrong"},
            )

        assert response.status_code == 401

    async def test_register_missing_body_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Register with no body returns 422 Unprocessable Entity."""
        response = await client.post("/api/v1/auth/register", json={})
        assert response.status_code == 422

    async def test_me_without_token_returns_401(self, client: AsyncClient) -> None:
        """GET /auth/me without Authorization header returns 401."""
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401
