"""Back-compat shim for the ``OfferLeadMagnet`` model.

The offers models were extracted into the mountable ``tribunal-offers`` block
(``backend/packages/offers``). The live definition lives in
``tribunal_offers.models``; this module re-exports it so that:

* existing imports (``from app.models.offer_lead_magnet import OfferLeadMagnet``)
  keep working,
* importing this module registers the ``offer_lead_magnets`` table in
  ``Base.metadata`` so ``app.db.model_registry.import_model_modules`` still
  discovers it for Alembic.
"""

from __future__ import annotations

from tribunal_offers.models import OfferLeadMagnet

__all__ = ["OfferLeadMagnet"]
