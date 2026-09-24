"""Vertical kit catalog and evidence-gated proof calculations."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from tribunal_lead_capture.service import build_lead_magnet_email_body

from app.services.offers.roi_proof import FunnelPeriod, benchmark_context, build_proof_pack
from app.services.offers.vertical_drafts import build_vertical_drafts
from app.services.offers.vertical_kits import (
    VERTICAL_KITS,
    get_vertical_campaign_copy,
    get_vertical_kit,
)


def period(label: str, source: str, start: str, end: str, **overrides: object) -> FunnelPeriod:
    fields = {
        "label": label,
        "source": source,
        "starts_at": start,
        "ends_at": end,
        "attempts": 100,
        "connected": 40,
        "qualified": 20,
        "booked": 15,
        "qualified_meetings": 10,
        "shown": 9,
        "total_cost_usd": Decimal("2400"),
    }
    fields.update(overrides)
    return FunnelPeriod(**fields)


def test_vertical_kits_are_complete_and_campaign_compatible() -> None:
    assert set(VERTICAL_KITS) == {"real_estate", "roofing", "hvac"}
    for key in VERTICAL_KITS:
        kit = get_vertical_kit(key)
        assert kit.offer and kit.qualification and kit.objections
        assert kit.evidence_to_collect and kit.compliance_addendum
        drafts = build_vertical_drafts(key)
        assert drafts.offer.is_active is False
        assert drafts.lead_magnet.is_active is False
        assert drafts.lead_magnet.content_data is not None
        assert kit.voice_script in drafts.lead_magnet.content_data["body"]
        assert all(reply in drafts.lead_magnet.content_data["body"] for _, reply in kit.objections)
        email = build_lead_magnet_email_body(
            lead_magnet=SimpleNamespace(**drafts.lead_magnet.model_dump()),
            offer_name=drafts.offer.name,
        )
        assert kit.voice_script in email
        assert all(reply in email for _, reply in kit.objections)
        assert get_vertical_campaign_copy(key) == {
            "name": kit.name,
            "initial_message": kit.initial_sms,
            "follow_up_message": kit.follow_up_sms,
        }
        assert "AI assistant" in kit.voice_script
        for message in (kit.initial_sms, kit.follow_up_sms):
            assert "{first_name}" in message
            assert "STOP" in message
            assert "{" not in message.replace("{first_name}", "")


def test_proof_pack_calculates_percentage_points_not_relative_growth() -> None:
    before = period("before", "export-before", "2026-01-01", "2026-02-01")
    after = period(
        "after",
        "export-after",
        "2026-02-01",
        "2026-03-01",
        connected=50,
        qualified=25,
        booked=20,
        qualified_meetings=12,
        shown=16,
        total_cost_usd=Decimal("2880"),
    )
    proof = build_proof_pack(before, after)
    assert proof["before"]["cost_per_qualified_meeting_usd"] == Decimal("240")
    assert proof["after"]["cost_per_qualified_meeting_usd"] == Decimal("240")
    assert proof["lift_percentage_points"]["connect_rate"] == Decimal("10.0")
    assert proof["lift_percentage_points"]["show_rate"] == Decimal("20.0")
    assert proof["publishable"] is False


def test_brief_benchmark_is_arithmetic_only_not_customer_proof() -> None:
    context = benchmark_context()
    assert context["difference_usd"] == Decimal("263")
    assert round(context["lower_fraction"] * 100) == 54
    assert "unverified" in context["source"]
    assert context["publishable"] is False


def test_no_denominator_does_not_create_a_claim() -> None:
    empty = period(
        "before",
        "before",
        "2026-01-01",
        "2026-02-01",
        attempts=0,
        connected=0,
        qualified=0,
        booked=0,
        qualified_meetings=0,
        shown=0,
    )
    after = period("after", "after", "2026-02-01", "2026-03-01")
    proof = build_proof_pack(empty, after)
    assert proof["before"]["connect_rate"] is None
    assert proof["before"]["cost_per_qualified_meeting_usd"] is None
    assert proof["lift_percentage_points"]["connect_rate"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"qualified_meetings": 16},
        {"shown": 16},
        {"connected": 101},
        {"total_cost_usd": Decimal("NaN")},
        {"attempts": -1},
    ],
)
def test_invalid_evidence_is_rejected(changes: dict) -> None:
    with pytest.raises(ValueError):
        period("before", "before", "2026-01-01", "2026-02-01", **changes)


def test_overlapping_or_same_source_windows_are_rejected() -> None:
    before = period("before", "same", "2026-01-01", "2026-02-10")
    with pytest.raises(ValueError):
        build_proof_pack(before, period("after", "other", "2026-02-01", "2026-03-01"))
    with pytest.raises(ValueError):
        build_proof_pack(before, period("after", "same", "2026-02-10", "2026-03-01"))
