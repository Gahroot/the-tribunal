"""Back-compat shim for the ``LeadMagnetLead`` model.

The lead-capture models were extracted into the mountable
``tribunal-lead-capture`` block (``backend/packages/lead-capture``). The live
definition lives in ``tribunal_lead_capture.models``; this module re-exports it
so that:

* existing imports (``from app.models.lead_magnet_lead import LeadMagnetLead``)
  keep working,
* importing this module registers the ``lead_magnet_leads`` table in
  ``Base.metadata`` so ``app.db.model_registry.import_model_modules`` still
  discovers it for Alembic.
"""

from __future__ import annotations

from tribunal_lead_capture.models import LeadMagnetLead

__all__ = ["LeadMagnetLead"]
