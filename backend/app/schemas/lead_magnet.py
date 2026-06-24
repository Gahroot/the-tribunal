"""Back-compat shim for the lead-magnet schemas.

The schemas were extracted into the mountable ``tribunal-lead-capture`` block
(``backend/packages/lead-capture``). The live definitions live in
``tribunal_lead_capture.schemas``; this module re-exports them so existing
imports (``from app.schemas.lead_magnet import LeadMagnetResponse``) keep working.
"""

from __future__ import annotations

from tribunal_lead_capture.schemas import (
    CalculatorCalculation,
    CalculatorCTA,
    CalculatorGenerationRequest,
    CalculatorInput,
    CalculatorOutput,
    CalculatorSelectOption,
    DeliveryMethod,
    GeneratedCalculatorContent,
    GeneratedQuizContent,
    LeadMagnetBase,
    LeadMagnetCreate,
    LeadMagnetResponse,
    LeadMagnetType,
    LeadMagnetUpdate,
    OfferLeadMagnetCreate,
    OfferLeadMagnetResponse,
    PaginatedLeadMagnets,
    QuizGenerationRequest,
    QuizOption,
    QuizQuestion,
    QuizResult,
)

__all__ = [
    "CalculatorCalculation",
    "CalculatorCTA",
    "CalculatorGenerationRequest",
    "CalculatorInput",
    "CalculatorOutput",
    "CalculatorSelectOption",
    "DeliveryMethod",
    "GeneratedCalculatorContent",
    "GeneratedQuizContent",
    "LeadMagnetBase",
    "LeadMagnetCreate",
    "LeadMagnetResponse",
    "LeadMagnetType",
    "LeadMagnetUpdate",
    "OfferLeadMagnetCreate",
    "OfferLeadMagnetResponse",
    "PaginatedLeadMagnets",
    "QuizGenerationRequest",
    "QuizOption",
    "QuizQuestion",
    "QuizResult",
]
