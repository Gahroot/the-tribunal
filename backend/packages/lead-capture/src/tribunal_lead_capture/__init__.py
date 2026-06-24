"""Mountable contract for the ``lead-capture`` block (lead forms + lead magnets).

A host FastAPI app integrates this block through exactly these names::

    from tribunal_lead_capture import (
        get_router,
        get_public_router,
        deliver_lead_magnet_to_lead,
    )

* ``get_router()`` returns the authenticated, workspace-scoped router (lead-magnet
  authoring under ``/workspaces/{workspace_id}/lead-magnets`` + lead-source config
  under ``/workspaces/{workspace_id}/lead-sources``). Mount with
  ``app.include_router(get_router())`` — the prefixes + tags are baked in.
* ``get_public_router()`` returns the no-auth public lead-form router mounted at
  ``/p/leads`` (origin-validated, IP-rate-limited). Preserves the exact public URL
  ``/api/v1/p/leads/{public_key}`` embedded forms post to.
* ``deliver_lead_magnet_to_lead`` / ``build_lead_magnet_email_body`` are the
  block's public service API — the offers block calls them on opt-in to email the
  promised magnet.
* ``models`` (re-exported ``LeadMagnet`` / ``LeadMagnetLead`` / ``LeadSource`` +
  enums) bind to the shared ``Base`` so their tables register in ``Base.metadata``
  for Alembic. The host imports them via the back-compat shims in ``app.models``.

This block owns no background workers, so it exposes no ``register_workers``.

Only the lightweight :mod:`~tribunal_lead_capture.models` and
:mod:`~tribunal_lead_capture.schemas` are imported eagerly. The routers and the
delivery service (which pull ``app.core_api`` plus the host's voice / agent-brain
/ messaging / sla service graph) are exposed lazily via :pep:`562`
``__getattr__`` so importing the *models* — e.g. when Alembic's model registry
imports the ``app.models.lead_magnet`` shim during startup — does not drag the
heavy runtime graph in before it is ready.

See ``docs/blocks/BACKEND_BLOCK_PATTERN.md`` for the full pattern.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .models import (
    DeliveryMethod,
    LeadMagnet,
    LeadMagnetLead,
    LeadMagnetType,
    LeadSource,
    generate_lead_source_key,
)

if TYPE_CHECKING:
    from .router import get_public_router, get_router
    from .service import build_lead_magnet_email_body, deliver_lead_magnet_to_lead

# Lazy attribute -> (submodule, attribute) map for the heavy runtime surface.
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "get_router": (".router", "get_router"),
    "get_public_router": (".router", "get_public_router"),
    "deliver_lead_magnet_to_lead": (".service", "deliver_lead_magnet_to_lead"),
    "build_lead_magnet_email_body": (".service", "build_lead_magnet_email_body"),
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
    "deliver_lead_magnet_to_lead",
    "build_lead_magnet_email_body",
    # Models (eager — light, only the shared Base)
    "LeadMagnet",
    "LeadMagnetLead",
    "LeadSource",
    "LeadMagnetType",
    "DeliveryMethod",
    "generate_lead_source_key",
]
