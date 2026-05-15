"""Tests for CORS origin allow-list.

The production CORS regex must allow Vercel preview deployments under the
project's own team (`ngrout70-6776s-projects`) but reject any other
`*.vercel.app` origin. A previous version of the regex accepted any
`*.vercel.app` subdomain, which let any attacker who deployed to Vercel hit
the cookie-auth API.
"""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient

from app.main import app as production_app


def _build_pattern_from_settings() -> str:
    """Rebuild the CORS regex the same way ``app.main`` does, in isolation.

    Mirrors the construction in ``backend/app/main.py`` so the test exercises
    the actual regex shape without depending on import-time middleware order.
    """
    import re

    from app.core.config import settings

    origins = set(settings.cors_origins)
    if settings.frontend_url:
        origins.add(settings.frontend_url)
    escaped = [re.escape(o) for o in origins]
    vercel_team_pattern = r"https://[a-z0-9-]+-ngrout70-6776s-projects\.vercel\.app"
    return "^(?:" + "|".join(escaped) + "|" + vercel_team_pattern + ")$"


def _make_cors_app() -> FastAPI:
    """Build a minimal app with the production CORS regex attached."""
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=_build_pattern_from_settings(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "Origin",
            "X-Requested-With",
        ],
    )

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"ok": "ok"}

    return app


@pytest.fixture
async def cors_client() -> AsyncIterator[AsyncClient]:
    """HTTP client bound to a minimal app wired with the production CORS regex."""
    app = _make_cors_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


async def _preflight(client: AsyncClient, origin: str) -> str | None:
    """Send a CORS preflight and return the echoed ``access-control-allow-origin``.

    Returns ``None`` when the middleware refuses to echo the origin (the
    request is rejected from a CORS standpoint even though Starlette still
    returns 200 for the OPTIONS handler).
    """
    response = await client.options(
        "/ping",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    value = response.headers.get("access-control-allow-origin")
    return value if value is None else str(value)


class TestVercelCorsAllowList:
    """The CORS regex only trusts the project's own Vercel team."""

    async def test_team_preview_origin_is_allowed(
        self, cors_client: AsyncClient
    ) -> None:
        """A preview under ``ngrout70-6776s-projects`` is echoed back."""
        origin = "https://aicrm-abc123-ngrout70-6776s-projects.vercel.app"
        echoed = await _preflight(cors_client, origin)
        assert echoed == origin

    async def test_foreign_vercel_origin_is_rejected(
        self, cors_client: AsyncClient
    ) -> None:
        """A ``*.vercel.app`` origin outside the team is NOT echoed back.

        This is the regression case: the old regex
        ``https://[a-z0-9-]+\\.vercel\\.app`` matched any tenant's deployment.
        """
        origin = "https://evil-attacker.vercel.app"
        echoed = await _preflight(cors_client, origin)
        assert echoed is None, (
            f"Foreign Vercel origin {origin} must not be allowed by CORS; "
            f"got Access-Control-Allow-Origin={echoed!r}"
        )

    async def test_foreign_team_preview_is_rejected(
        self, cors_client: AsyncClient
    ) -> None:
        """A preview under a different team slug is NOT echoed back."""
        origin = "https://aicrm-abc123-someoneelses-projects.vercel.app"
        echoed = await _preflight(cors_client, origin)
        assert echoed is None

    async def test_team_slug_as_root_subdomain_is_rejected(
        self, cors_client: AsyncClient
    ) -> None:
        """An origin spoofing the team slug as the only subdomain is rejected.

        ``https://ngrout70-6776s-projects.vercel.app`` is NOT a real Vercel
        preview URL — real previews always have ``<project>-<hash>-`` in
        front of the team slug.
        """
        origin = "https://ngrout70-6776s-projects.vercel.app"
        echoed = await _preflight(cors_client, origin)
        assert echoed is None

    async def test_localhost_origin_still_allowed(
        self, cors_client: AsyncClient
    ) -> None:
        """The default ``http://localhost:3000`` origin remains allowed."""
        origin = "http://localhost:3000"
        echoed = await _preflight(cors_client, origin)
        assert echoed == origin


class TestProductionAppCorsRegex:
    """Sanity check that the live ``app.main`` app uses the locked-down regex."""

    def test_app_regex_does_not_match_foreign_vercel(self) -> None:
        """No middleware on the real app accepts a foreign ``*.vercel.app``."""
        import re

        # Find the CORSMiddleware instance attached to the production app.
        cors_layers = [
            m
            for m in production_app.user_middleware
            if getattr(m.cls, "__name__", None) == CORSMiddleware.__name__
        ]
        assert cors_layers, "Production app must register CORSMiddleware"
        pattern_obj = cors_layers[0].kwargs.get("allow_origin_regex")
        assert isinstance(pattern_obj, str) and pattern_obj, (
            "Production CORSMiddleware must use allow_origin_regex (str), not a "
            "wildcard allow_origins list"
        )

        compiled = re.compile(pattern_obj)
        assert compiled.match(
            "https://aicrm-abc123-ngrout70-6776s-projects.vercel.app"
        )
        assert not compiled.match("https://evil-attacker.vercel.app")
        assert not compiled.match(
            "https://aicrm-abc123-someoneelses-projects.vercel.app"
        )
