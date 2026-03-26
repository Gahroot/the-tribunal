"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.v1.router import api_router
from app.api.webhooks.calcom import router as calcom_webhook_router
from app.api.webhooks.telnyx import router as telnyx_webhook_router
from app.core.config import settings
from app.db.redis import close_redis
from app.websockets.voice_bridge import router as voice_bridge_router
from app.websockets.voice_test import router as voice_test_router
from app.workers import start_all_workers, stop_all_workers

logger = structlog.get_logger()


class SecurityHeadersMiddleware:
    """Pure ASGI middleware to add security headers to all responses."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        connect_sources = ["'self'", "wss:", "https://api.openai.com", "https://api.telnyx.com", "https://api.elevenlabs.io"]
        for origin in settings.cors_origins:
            if origin not in connect_sources:
                connect_sources.append(origin)
        self._csp = "; ".join([
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: https:",
            "font-src 'self'",
            f"connect-src {' '.join(connect_sources)}",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ])

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                headers = MutableHeaders(scope=message)
                headers["X-Frame-Options"] = "DENY"
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
                headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
                headers["Content-Security-Policy"] = self._csp
            await send(message)

        await self.app(scope, receive, send_with_headers)


def _validate_startup_config() -> None:
    """Validate required configuration at startup.

    Checks for critical API keys and settings needed for application functionality.
    Logs warnings for incomplete integrations.
    """
    log = logger.bind(context="startup_validation")

    # Check required API keys
    if not settings.openai_api_key:
        log.warning("missing_openai_api_key", severity="critical")

    if not settings.telnyx_api_key:
        log.warning("missing_telnyx_api_key", severity="critical")

    # Check optional but important integrations
    if not settings.calcom_api_key:
        log.warning("missing_calcom_api_key", message="Cal.com appointments disabled")

    if not settings.elevenlabs_api_key:
        log.warning("missing_elevenlabs_api_key", message="ElevenLabs voice disabled")

    # Check Telnyx webhook configuration
    if not settings.telnyx_public_key and not settings.skip_webhook_verification:
        log.warning(
            "missing_telnyx_public_key",
            message="Telnyx webhook verification disabled",
        )

    # Check secret key security
    if settings.secret_key == "change-me-in-production":
        if not settings.debug:
            log.error(
                "insecure_secret_key",
                severity="critical",
                message="Using default secret_key in production is not allowed",
            )
            raise RuntimeError(
                "SECRET_KEY must be set in production. "
                "Default value 'change-me-in-production' is insecure."
            )
        else:
            log.warning(
                "default_secret_key",
                severity="medium",
                message="Using default secret_key in development mode",
            )

    # Warn if webhook verification is disabled in non-debug mode
    if settings.skip_webhook_verification and not settings.debug:
        log.warning(
            "webhook_verification_disabled",
            severity="high",
            message="Webhook verification is disabled in production",
        )

    # Check database configuration
    if "localhost" in settings.database_url and not settings.debug:
        log.warning(
            "localhost_database_url",
            severity="high",
            message="Using localhost database URL in non-debug mode",
        )

    log.info("startup_validation_complete")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    log = logger.bind(context="app_lifespan")
    log.info("Starting AI CRM backend...")

    # Validate configuration at startup
    _validate_startup_config()

    # Start all background workers
    await start_all_workers()

    yield

    log.info("Shutting down AI CRM backend...")
    await stop_all_workers()
    await close_redis()


app = FastAPI(
    title="AI CRM API",
    description="AI-powered CRM with voice agents, SMS campaigns, and Cal.com integration",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# Security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
)

# Include API router
app.include_router(api_router, prefix="/api/v1")

# Include webhook routers
app.include_router(telnyx_webhook_router, prefix="/webhooks/telnyx", tags=["webhooks"])
app.include_router(calcom_webhook_router, prefix="/webhooks/calcom", tags=["webhooks"])

# Include WebSocket routers
app.include_router(voice_bridge_router, tags=["voice"])
app.include_router(voice_test_router, tags=["voice"])

# Mount static files for lead magnets and other assets
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global handler for unhandled exceptions.

    Logs the full error internally but returns a generic message to the client
    to avoid leaking internal details.
    """
    logger.error("unhandled_exception", exc_info=exc, path=str(request.url))
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
