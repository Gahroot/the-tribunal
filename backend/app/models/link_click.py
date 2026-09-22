"""Back-compat shim for the ``LinkClick`` model.

The short-link models were extracted into the mountable ``tribunal-short-links``
block (``backend/packages/short-links``). The live definition lives in
``tribunal_short_links.models``; this module re-exports it so that:

* existing imports (``from app.models.link_click import LinkClick``) keep working,
* importing this module registers the ``link_clicks`` table in ``Base.metadata``,
  so ``app.db.model_registry.import_model_modules`` still discovers it for Alembic.
"""

from __future__ import annotations

from tribunal_short_links.models import LinkClick

__all__ = ["LinkClick"]
