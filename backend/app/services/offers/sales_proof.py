"""Internal sales enablement exports. Never publish or send customer records here."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.services.offers.roi_proof import FunnelPeriod, benchmark_context, build_proof_pack
from app.services.offers.vertical_kits import SHARED_RULES, get_vertical_kit


class CaseStudyEvidence(BaseModel):
    """Aggregate evidence only; no contact details or transcripts in this export.

    References identify privately stored evidence; they are not fetched or verified.
    Human approval cannot be granted by setting a field in the input JSON.
    """

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    customer_alias: str = Field(min_length=1, max_length=120)
    problem: str = Field(min_length=1, max_length=2000)
    interventions: list[str] = Field(min_length=1, max_length=12)
    qualification_definition: str = Field(min_length=1, max_length=2000)
    cost_basis: str = Field(min_length=1, max_length=2000)
    limitations: str = Field(min_length=1, max_length=2000)
    permission_reference: str = Field(min_length=1, max_length=500)
    before: FunnelPeriod
    after: FunnelPeriod


def build_sales_proof(vertical: str, evidence: CaseStudyEvidence | None = None) -> dict[str, Any]:
    """Bundle the vertical sales story, review gates and optional measured arithmetic."""
    kit = get_vertical_kit(vertical)
    result: dict[str, Any] = {
        "status": "internal draft; not approved for publication",
        "publishable": False,
        "vertical": vertical,
        "buyer": kit.audience,
        "system_pitch": (
            f"The Tribunal helps {kit.audience.lower()} qualify inquiries, "
            "coordinate follow-up and request appointments with human oversight. "
            "Evaluate it against your own baseline; no outcome is guaranteed."
        ),
        "pilot_acceptance": {
            "qualified_meeting_checklist": kit.qualification,
            "success_rule": (
                "Agree on a target and matched baseline before the pilot; do not invent a lift."
            ),
            "deliverables": [
                "Reviewed voice/SMS scripts and objection library",
                "Inactive offer and response-playbook lead magnet",
                "Source-referenced connection, booking and attendance comparison",
                "All-in cost per qualified meeting, with cost inclusions disclosed",
            ],
        },
        "proof_assets": kit.evidence_to_collect,
        "compliance_addendum": (*SHARED_RULES, *kit.compliance_addendum),
        "legal_notice": "Engineering guidance, not legal advice; local counsel review required.",
        "benchmark_context": benchmark_context(),
        "review_gates": [
            "Sales: verify exports and permission to publish each asset or customer story.",
            "Operations: reconcile counts, attribution, costs and matched cohort definitions.",
            "Counsel: approve consent, recordings and vertical advertising claims.",
            "Benchmark: independently source the $224/$487 comparison "
            "before using it in sales copy.",
        ],
        "case_study": None,
    }
    if evidence is not None:
        if any(not item.strip() for item in evidence.interventions):
            raise ValueError("Interventions must not be blank")
        result["case_study"] = {
            "title": f"{evidence.customer_alias} — {kit.name}",
            "evidence": evidence.model_dump(mode="json"),
            "results": build_proof_pack(evidence.before, evidence.after),
            "interpretation": (
                "Observed arithmetic from supplied aggregates, not independently verified. "
                "Before/after differences do not establish causation. Rates use attempts, "
                "except show rate which uses bookings. Windows are start-inclusive, end-exclusive."
            ),
        }
    return result
