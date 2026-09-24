"""Draft vertical assets for the existing offer and lead-magnet creation APIs.

No records are persisted and no campaigns are started by this module. Review
branding, consent, jurisdiction, and customer-facing copy before activation.
"""

from dataclasses import dataclass

from tribunal_lead_capture.schemas import DeliveryMethod, LeadMagnetCreate, LeadMagnetType
from tribunal_offers.schemas import OfferCreate

from app.services.offers.vertical_kits import get_vertical_campaign_copy, get_vertical_kit


@dataclass(frozen=True)
class VerticalDrafts:
    offer: OfferCreate
    lead_magnet: LeadMagnetCreate
    campaign_copy: dict[str, str]


def build_vertical_drafts(vertical: str) -> VerticalDrafts:
    """Build inactive drafts accepted by existing offer/lead-magnet endpoints.

    Attach the returned lead magnet to the offer through the existing offer
    lead-magnet association endpoint only after both drafts are reviewed.
    """
    kit = get_vertical_kit(vertical)
    playbook = "\n".join(
        [
            f"{kit.name} — playbook",
            kit.offer,
            "Qualification: " + "; ".join(kit.qualification),
            "Opening: " + kit.voice_script,
            "Common questions:",
            *(f"{question} — {reply}" for question, reply in kit.objections),
            "Operating rules: " + " ".join(kit.compliance_addendum),
        ]
    )
    return VerticalDrafts(
        offer=OfferCreate(
            name=kit.name,
            description=kit.offer,
            headline=kit.offer,
            cta_text="Request a consultation",
            is_active=False,
        ),
        lead_magnet=LeadMagnetCreate(
            name=f"{kit.name} playbook",
            description=f"Sample qualification questions and responses for {kit.audience}.",
            magnet_type=LeadMagnetType.RICH_TEXT,
            delivery_method=DeliveryMethod.EMAIL,
            content_data={"title": f"{kit.name} playbook", "body": playbook},
            is_active=False,
        ),
        campaign_copy=get_vertical_campaign_copy(vertical),
    )
