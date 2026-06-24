"""Health probes for the ``__BLOCK_ID__`` service.

Mirrors ``backend/app/api/v1/health.py``: ``/livez`` is process-up,
``/readyz`` is startup-complete (+ optional infra). Orchestrators probe **this
service's** ``/readyz`` — never the host's.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response, status

router = APIRouter()


@router.get("/livez", tags=["Health"])
async def livez() -> dict[str, str]:
    """Liveness probe — process is up. No external checks."""
    return {"status": "ok"}


@router.get("/readyz", tags=["Health"])
async def readyz(request: Request, response: Response) -> dict[str, Any]:
    """Readiness probe — startup complete + the service's own deps reachable.

    Returns 503 until ``app.state.ready`` flips (the lifespan handler sets it once
    config is validated and the worker has started). Add infra checks (Postgres
    slice, Redis) here when the service owns state — see the host's
    ``backend/app/api/v1/health.py`` for the ``SELECT 1`` / ``PING`` shape.
    """
    startup_ready = bool(getattr(request.app.state, "ready", False))
    if not startup_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "starting",
            "checks": {"startup": {"ok": False, "error": "startup_incomplete"}},
        }
    return {"status": "ok", "checks": {"startup": {"ok": True, "error": None}}}
