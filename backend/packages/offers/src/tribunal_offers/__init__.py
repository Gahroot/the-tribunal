"""Mountable contract for the ``offers`` block (Offers & Offer Builder).

A host FastAPI app integrates this block through exactly these names::

    from tribunal_offers import get_router, get_public_router

* ``get_router()`` returns the authenticated, workspace-scoped offer authoring
  router (``/workspaces/{workspace_id}/offers``). Mount with
  ``app.include_router(get_router())`` — the prefix + tags are baked in.
* ``get_public_router()`` returns the no-auth public offer opt-in router
  (``/p/offers``), preserving the exact public URLs
  ``/api/v1/p/offers/{slug}`` and ``/api/v1/p/offers/{slug}/opt-in``. Mount it the
  same way.
* ``models`` (re-exported ``Offer`` / ``OfferLeadMagnet``) bind to the shared
  ``Base`` so their tables register in ``Base.metadata`` for Alembic. The host
  imports them via the back-compat shims in ``app.models``.
* ``prestyj_batch_video_ads`` is the static productized-offer pack definition
  module (``format_pack_terms``, pack/pricing helpers) — also re-exported through
  the back-compat shim at ``app.services.offers.prestyj_batch_video_ads``.

This block owns no background workers, so it exposes no ``register_workers``.

Only the lightweight :mod:`~tribunal_offers.models` are imported eagerly. The
router and schemas (which pull ``app.core_api`` plus the host's agent-brain /
lead-capture / contacts graph) are exposed lazily via :pep:`562` ``__getattr__``
so that importing the *models* — e.g. when Alembic's model registry imports the
``app.models.offer`` shim during startup — does not drag the heavy runtime graph
in before it is ready.

See ``docs/blocks/BACKEND_BLOCK_PATTERN.md`` for the full pattern.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .models import Offer, OfferLeadMagnet

if TYPE_CHECKING:
    from .prestyj_batch_video_ads import format_pack_terms
    from .router import get_public_router, get_router

# Lazy attribute -> (submodule, attribute) map for the heavy runtime surface.
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "get_router": (".router", "get_router"),
    "get_public_router": (".router", "get_public_router"),
    "format_pack_terms": (".prestyj_batch_video_ads", "format_pack_terms"),
}


def __getattr__(name: str) -> Any:
    """Lazily resolve the runtime surface (PEP 562) to avoid early import cycles."""
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    module_name, attr = target
    module = import_module(module_name, __name__)
    return getattr(module, attr)


__all__ = [
    # Runtime contract (lazy)
    "get_router",
    "get_public_router",
    # Public service API (lazy)
    "format_pack_terms",
    # Models (eager — light, only the shared Base)
    "Offer",
    "OfferLeadMagnet",
]
