"""Back-compat shim for the public embed endpoints.

The public embed surface was extracted into the mountable ``tribunal-widget``
block (``backend/packages/widget``). The live router is built by
``tribunal_widget.get_router()`` and mounted in ``app/api/v1/router.py``.

This module remains only as a thin compatibility surface:

* ``router`` re-exposes the block's router for any legacy importer.
* ``_check_embed_rate_limits`` adapts the block's per-phone/IP rate-limit check
  for callers that exercise it directly.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from tribunal_widget import get_router
from tribunal_widget.access import EmbedAccessService

# The block's router already carries the ``/p/embed`` prefix and ``Public Embed``
# tag; the v1 aggregator mounts ``get_router()`` directly.
router = get_router()


async def _check_embed_rate_limits(
    db: AsyncSession,
    client_ip: str,
    phone_number: str,
) -> None:
    """Enforce the DB-backed IP/phone rate limits for embed call/text requests."""
    await EmbedAccessService(db).enforce_phone_limit(
        client_ip=client_ip,
        phone_number=phone_number,
    )
