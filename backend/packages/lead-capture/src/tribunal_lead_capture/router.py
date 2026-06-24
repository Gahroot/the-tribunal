"""HTTP surface for the ``lead-capture`` block.

Two routers:

* ``get_router()`` — authenticated, workspace-scoped lead-magnet authoring and
  lead-source configuration. Combines two sub-routers, each carrying its own
  prefix + tags:
    - ``/workspaces/{workspace_id}/lead-magnets``  (Lead Magnets)
    - ``/workspaces/{workspace_id}/lead-sources``  (Lead Sources)
* ``get_public_router()`` — the no-auth, origin-validated, IP-rate-limited public
  lead form mounted at ``/p/leads``. This preserves the exact public URL
  ``/api/v1/p/leads/{public_key}`` that embedded website forms post to — do not
  change this prefix.

All prefixes + tags are baked into the routers so the host mounts them
prefix-free (``app.include_router(get_router())``). Core DI primitives come only
through ``app.core_api``; sibling-block services (voice Telnyx, agent-brain AI
generators, contacts/messaging models, SLA, push, email) are documented in the
block README.
"""

from __future__ import annotations

from fastapi import APIRouter

from ._lead_form import router as lead_form_router
from ._lead_magnets import router as lead_magnets_router
from ._lead_sources import router as lead_sources_router


def get_router() -> APIRouter:
    """Return the authenticated, workspace-scoped lead-capture router."""
    router = APIRouter()
    router.include_router(
        lead_magnets_router,
        prefix="/workspaces/{workspace_id}/lead-magnets",
        tags=["Lead Magnets"],
    )
    router.include_router(
        lead_sources_router,
        prefix="/workspaces/{workspace_id}/lead-sources",
        tags=["Lead Sources"],
    )
    return router


def get_public_router() -> APIRouter:
    """Return the no-auth public lead-form router (mounted at ``/p/leads``)."""
    router = APIRouter()
    router.include_router(
        lead_form_router,
        prefix="/p/leads",
        tags=["Public Lead Form"],
    )
    return router
