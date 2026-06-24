"""Back-compat shim for the lead-source schemas.

The schemas were extracted into the mountable ``tribunal-lead-capture`` block
(``backend/packages/lead-capture``). The live definitions live in
``tribunal_lead_capture.schemas``; this module re-exports them so existing
imports (``from app.schemas.lead_source import LeadSubmitRequest``) keep working.
"""

from __future__ import annotations

from tribunal_lead_capture.schemas import (
    LeadSourceCreate,
    LeadSourceResponse,
    LeadSourceUpdate,
    LeadSubmitRequest,
    LeadSubmitResponse,
)

__all__ = [
    "LeadSourceCreate",
    "LeadSourceResponse",
    "LeadSourceUpdate",
    "LeadSubmitRequest",
    "LeadSubmitResponse",
]
