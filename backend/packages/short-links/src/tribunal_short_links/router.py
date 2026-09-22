"""HTTP surface for the ``short-links`` block — the public redirect endpoint.

``get_router()`` is the only required runtime export. The single route
``GET /r/{short_code}`` is public by design (these are user-facing SMS URLs);
it carries no prefix, so the host mounts it at the app root to preserve the
existing short-link URLs exactly.

Core primitives come only through ``app.core_api`` (the DB session); the block
carries no sideways import into a sibling block.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from .service import record_click


def get_router() -> APIRouter:
    """Return the block's redirect router for ``app.include_router(...)``."""
    # Imported lazily inside the factory: the SMS sender reached via the
    # ``app.core_api`` worker graph imports this block's write API back, so a
    # module-level ``app.core_api`` import here would create an import cycle.
    from app.core_api import get_db

    router = APIRouter(tags=["redirects"])

    @router.get("/r/{short_code}")
    async def redirect_short_link(
        short_code: str,
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> RedirectResponse:
        """Resolve a short code, log the click, and 302 to the target URL."""
        short_link = await record_click(
            db,
            short_code=short_code,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            referer=request.headers.get("referer"),
        )
        if short_link is None:
            raise HTTPException(status_code=404, detail="Short link not found")

        return RedirectResponse(url=short_link.target_url, status_code=302)

    return router
