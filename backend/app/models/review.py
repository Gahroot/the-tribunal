"""Back-compat shim for the ``Review`` model.

The review models were extracted into the mountable ``tribunal-reviews`` block
(``backend/packages/reviews``). The live definition lives in
``tribunal_reviews.models``; this module re-exports it so that:

* existing imports (``from app.models.review import Review``) keep working,
* importing this module registers the ``reviews`` table in ``Base.metadata`` so
  ``app.db.model_registry.import_model_modules`` still discovers it for Alembic.
"""

from __future__ import annotations

from tribunal_reviews.models import (
    Review,
    ReviewSentiment,
    ReviewSource,
    ReviewStatus,
)

__all__ = ["Review", "ReviewSentiment", "ReviewSource", "ReviewStatus"]
