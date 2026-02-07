"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.api.v1.router import api_router
from app.api.webhooks.calcom import router as calcom_webhook_router
from app.api.webhooks.telnyx import router as telnyx_webhook_router
from app.core.config import settings
from app.db.redis import close_redis
from app.websockets.voice_bridge import router as voice_bridge_router
from app.websockets.voice_test import router as voice_test_router
from app.workers.campaign_worker import start_campaign_worker, stop_campaign_worker
from app.workers.enrichment_worker import (
    start_enrichment_worker,
    stop_enrichment_worker,
)
from app.workers.experiment_evaluation_worker import (
    start_experiment_evaluation_worker,
    stop_experiment_evaluation_worker,
)
from app.workers.followup_worker import start_followup_worker, stop_followup_worker
from app.workers.message_test_worker import (
    start_message_test_worker,
    stop_message_test_worker,
)
from app.workers.prompt_improvement_worker import (
    start_prompt_improvement_worker,
    stop_prompt_improvement_worker,
)
from app.workers.prompt_stats_worker import (
    start_prompt_stats_worker,
    stop_prompt_stats_worker,
)
from app.workers.reminder_worker import start_reminder_worker, stop_reminder_worker
from app.workers.reputation_worker import reputation_worker
from app.workers.voice_campaign_worker import (
    start_voice_campaign_worker,
    stop_voice_campaign_worker,
)

logger = structlog.get_logger()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response


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

    # Start background workers
    await start_campaign_worker()
    log.info("Campaign worker started")
    await start_voice_campaign_worker()
    log.info("Voice campaign worker started")
    await start_followup_worker()
    log.info("Follow-up worker started")
    await start_reminder_worker()
    log.info("Reminder worker started")
    await start_message_test_worker()
    log.info("Message test worker started")
    await reputation_worker.start()
    log.info("Reputation worker started")
    await start_enrichment_worker()
    log.info("Enrichment worker started")
    await start_prompt_stats_worker()
    log.info("Prompt stats worker started")
    await start_prompt_improvement_worker()
    log.info("Prompt improvement worker started")
    await start_experiment_evaluation_worker()
    log.info("Experiment evaluation worker started")

    yield

    log.info("Shutting down AI CRM backend...")
    # Stop background workers
    await stop_campaign_worker()
    log.info("Campaign worker stopped")
    await stop_voice_campaign_worker()
    log.info("Voice campaign worker stopped")
    await stop_followup_worker()
    log.info("Follow-up worker stopped")
    await stop_reminder_worker()
    log.info("Reminder worker stopped")
    await stop_message_test_worker()
    log.info("Message test worker stopped")
    await reputation_worker.stop()
    log.info("Reputation worker stopped")
    await stop_enrichment_worker()
    log.info("Enrichment worker stopped")
    await stop_prompt_stats_worker()
    log.info("Prompt stats worker stopped")
    await stop_prompt_improvement_worker()
    log.info("Prompt improvement worker stopped")
    await stop_experiment_evaluation_worker()
    log.info("Experiment evaluation worker stopped")
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


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
