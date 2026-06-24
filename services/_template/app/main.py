"""FastAPI app for the ``__BLOCK_ID__`` service.

A Level-3 standalone service: its own ASGI app, worker process, health probes,
and OpenAPI surface. The host CRM calls it over HTTP with a generated typed
client (see ``host_client/``) — it never imports this code.

See ``docs/blocks/SERVICE_BLOCK_PATTERN.md``.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from collections.abc import AsyncIterator

import structlog
from fastapi import FastAPI

from app import health, router
from app.config import settings
from app.worker import ServiceWorker

logger = structlog.get_logger()

# Worker lifecycle handles, owned by the lifespan.
_worker_task: asyncio.Task[None] | None = None
_worker_stop: asyncio.Event | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start the worker, mark the service ready, then drain on shutdown."""
    global _worker_task, _worker_stop
    log = logger.bind(context="service_lifespan", block=settings.block_id)

    if settings.run_worker:
        _worker_stop = asyncio.Event()
        _worker_task = asyncio.create_task(ServiceWorker().run(_worker_stop))
        log.info("worker_started")

    # Startup complete — /readyz now reports 200.
    app.state.ready = True
    log.info("service_ready")

    try:
        yield
    finally:
        # Flip ready off immediately so /readyz reports 503 during drain.
        app.state.ready = False
        if _worker_stop is not None:
            _worker_stop.set()
        if _worker_task is not None:
            with suppress(asyncio.TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(_worker_task, timeout=5)
        log.info("service_stopped")


app = FastAPI(
    title="__BLOCK_TITLE__ Service",
    description="__BLOCK_DESC__",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json",
)

# Business routes under /api/v1; health probes at root (Railway/K8s convention).
app.include_router(router.router, prefix="/api/v1", tags=["__BLOCK_ID__"])
app.include_router(health.router)


def export_openapi() -> None:
    """Print the service's OpenAPI schema as JSON.

    Used by a CI drift check analogous to ``make ci.codegen`` — check the JSON in
    and fail if the service's code and its committed ``openapi.json`` diverge.
    """
    import json

    print(json.dumps(app.openapi(), indent=2, default=str))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=settings.debug)
