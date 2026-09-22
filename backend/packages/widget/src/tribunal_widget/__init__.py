"""Mountable contract for the ``widget`` block (public embeddable chat/voice).

A host FastAPI app integrates this block through exactly these names::

    from tribunal_widget import get_router, register_providers

* ``get_router()`` returns the block's :class:`fastapi.APIRouter` (already
  prefixed ``/p/embed``); mount with ``api_router.include_router(get_router())``
  so the public routes live under ``/api/v1/p/embed/...``.
* ``register_providers(...)`` injects the sibling capabilities the block borrows
  (Telnyx SMS/voice and OpenAI credential resolution) so the block itself carries
  no sideways import into those blocks. See ``providers.py``.

This block owns no database tables and no background workers, so it exposes
neither ``models`` nor ``register_workers``.

See ``docs/blocks/BACKEND_BLOCK_PATTERN.md`` for the full pattern.
"""

from __future__ import annotations

from .providers import register_providers
from .router import get_router

__all__ = ["get_router", "register_providers"]
