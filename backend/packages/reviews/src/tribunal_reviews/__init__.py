"""Mountable contract for the ``reviews`` block (Reviews & Reputation engine).

A host FastAPI app integrates this block through exactly these names::

    from tribunal_reviews import get_router, get_public_router, register_workers

* ``get_router()`` returns the authenticated, workspace-scoped router
  (``/workspaces/{workspace_id}/reviews``). Mount with
  ``app.include_router(get_router())`` — the prefix + tags are baked in.
* ``get_public_router()`` returns the no-auth rating-gate landing-page router
  (``/p/reviews``); mount it the same way.
* ``register_workers(registry)`` appends the block's two background workers
  (``review_request_worker`` + ``reputation_worker``) to the host worker
  registry. ``review_request_registry`` / ``reputation_registry`` are also
  exported for hosts that wire a static worker spec list.
* ``ReviewService`` is the block's public write/read API — sibling blocks
  (appointment completion, dashboard, Cal.com webhook) call it instead of
  reaching into block internals.
* ``models`` (re-exported ``Review`` / ``ReviewRequest`` + enums) bind to the
  shared ``Base`` so their tables register in ``Base.metadata`` for Alembic. The
  host imports them via the back-compat shims in ``app.models``.

Only the lightweight :mod:`~tribunal_reviews.models` are imported eagerly. The
router / service / workers (which pull ``app.core_api`` and the host worker +
telephony graph) are exposed lazily via :pep:`562` ``__getattr__`` so that
importing the *models* — e.g. when Alembic's model registry imports the
``app.models.review`` shim during startup — does not drag the heavy runtime
graph in before it is ready (that ordering caused an import cycle).

See ``docs/blocks/BACKEND_BLOCK_PATTERN.md`` for the full pattern.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .models import (
    Review,
    ReviewRequest,
    ReviewRequestChannel,
    ReviewRequestStatus,
    ReviewSentiment,
    ReviewSource,
    ReviewStatus,
    generate_review_token,
)

if TYPE_CHECKING:
    from .router import get_public_router, get_router
    from .service import ReviewService
    from .workers import (
        ReputationWorker,
        ReviewRequestWorker,
        register_workers,
        reputation_registry,
        review_request_registry,
    )

# Lazy attribute -> (submodule, attribute) map for the heavy runtime surface.
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "get_router": (".router", "get_router"),
    "get_public_router": (".router", "get_public_router"),
    "ReviewService": (".service", "ReviewService"),
    "register_workers": (".workers", "register_workers"),
    "review_request_registry": (".workers", "review_request_registry"),
    "reputation_registry": (".workers", "reputation_registry"),
    "ReviewRequestWorker": (".workers", "ReviewRequestWorker"),
    "ReputationWorker": (".workers", "ReputationWorker"),
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
    "register_workers",
    # Public service API (lazy)
    "ReviewService",
    # Worker registries (lazy)
    "review_request_registry",
    "reputation_registry",
    "ReviewRequestWorker",
    "ReputationWorker",
    # Models (eager — light, only the shared Base)
    "Review",
    "ReviewRequest",
    "ReviewRequestChannel",
    "ReviewRequestStatus",
    "ReviewSentiment",
    "ReviewSource",
    "ReviewStatus",
    "generate_review_token",
]
