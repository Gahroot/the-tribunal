"""Back-compat shim for the offer schemas.

The schemas were extracted into the mountable ``tribunal-offers`` block
(``backend/packages/offers``). The live definitions live in
``tribunal_offers.schemas``; this module re-exports them so existing imports
(``from app.schemas.offer import OfferCreate``) keep working.
"""

from __future__ import annotations

from tribunal_offers.schemas import (
    DiscountType,
    GeneratedBonusIdea,
    GeneratedCTA,
    GeneratedGuarantee,
    GeneratedHeadline,
    GeneratedOfferContent,
    GeneratedSubheadline,
    GeneratedUrgency,
    GeneratedValueStackItem,
    GuaranteeType,
    NegotiationStep,
    OfferBase,
    OfferCreate,
    OfferCreateWithLeadMagnets,
    OfferGenerationRequest,
    OfferPack,
    OfferResponse,
    OfferResponseWithLeadMagnets,
    OfferStrategyMetadata,
    OfferUpdate,
    OptInRequest,
    OptInResponse,
    PaginatedOffers,
    PublicOfferResponse,
    UrgencyType,
    ValueStackItem,
)

__all__ = [
    "DiscountType",
    "GeneratedBonusIdea",
    "GeneratedCTA",
    "GeneratedGuarantee",
    "GeneratedHeadline",
    "GeneratedOfferContent",
    "GeneratedSubheadline",
    "GeneratedUrgency",
    "GeneratedValueStackItem",
    "GuaranteeType",
    "NegotiationStep",
    "OfferBase",
    "OfferCreate",
    "OfferCreateWithLeadMagnets",
    "OfferGenerationRequest",
    "OfferPack",
    "OfferResponse",
    "OfferResponseWithLeadMagnets",
    "OfferStrategyMetadata",
    "OfferUpdate",
    "OptInRequest",
    "OptInResponse",
    "PaginatedOffers",
    "PublicOfferResponse",
    "UrgencyType",
    "ValueStackItem",
]
