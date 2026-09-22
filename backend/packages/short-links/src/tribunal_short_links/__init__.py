"""Mountable contract for the ``short-links`` block (tracked SMS short URLs).

A host FastAPI app integrates this block through exactly these names::

    from tribunal_short_links import get_router, shorten_urls_in_text

* ``get_router()`` returns the block's :class:`fastapi.APIRouter` carrying the
  public ``GET /r/{short_code}`` redirect. It has no prefix; mount it at the app
  root (``app.include_router(get_router())``) to preserve existing short links.
* ``shorten_urls_in_text(...)`` is the block's public **write API**: SMS senders
  in sibling blocks call it to rewrite outbound URLs into tracked short links,
  instead of importing this block's internals. ``shorten_url`` is an alias.
* ``models`` (re-exported ``ShortLink`` / ``LinkClick``) bind to the shared
  ``Base`` so their tables register in ``Base.metadata`` for Alembic. The host
  imports them via the back-compat shims in ``app.models`` (see those modules).

This block owns no background workers, so it exposes no ``register_workers``.

See ``docs/blocks/BACKEND_BLOCK_PATTERN.md`` for the full pattern.
"""

from __future__ import annotations

from .models import LinkClick, ShortLink
from .router import get_router
from .service import record_click, shorten_urls_in_text

# Domain-friendly alias for the public write API.
shorten_url = shorten_urls_in_text

__all__ = [
    "get_router",
    "shorten_urls_in_text",
    "shorten_url",
    "record_click",
    "ShortLink",
    "LinkClick",
]
