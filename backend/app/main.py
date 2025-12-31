"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.api.webhooks.telnyx import router as telnyx_webhook_router
from app.core.config import settings
from app.db.redis import close_redis
from app.workers.campaign_worker import start_campaign_worker, stop_campaign_worker

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    logger.info("Starting AI CRM backend...")
    # Start background workers
    await start_campaign_worker()
    logger.info("Campaign worker started")
    yield
    logger.info("Shutting down AI CRM backend...")
    # Stop background workers
    await stop_campaign_worker()
    logger.info("Campaign worker stopped")
    await close_redis()


app = FastAPI(
    title="AI CRM API",
    description="AI-powered CRM with voice agents, SMS campaigns, and Cal.com integration",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix="/api/v1")

# Include webhook routers
app.include_router(telnyx_webhook_router, prefix="/webhooks/telnyx", tags=["webhooks"])


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
