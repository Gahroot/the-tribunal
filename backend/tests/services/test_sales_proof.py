"""Exercise the operator export with synthetic aggregates, never customer claims."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.services.offers.sales_proof import CaseStudyEvidence, build_sales_proof
from app.services.offers.vertical_drafts import build_vertical_drafts
from app.services.offers.vertical_kits import SHARED_RULES, VERTICAL_KITS

FIXTURE = Path(__file__).parents[3] / "docs/strategy/proof-example.synthetic.json"


def test_synthetic_case_study_math_and_provenance() -> None:
    evidence = CaseStudyEvidence.model_validate_json(FIXTURE.read_text())
    proof = build_sales_proof("real_estate", evidence)
    study = proof["case_study"]
    assert study["results"]["lift_percentage_points"]["connect_rate"] == 10
    assert study["results"]["lift_percentage_points"]["show_rate"] == 20
    assert study["results"]["before"]["cost_per_qualified_meeting_usd"] == 487
    assert study["results"]["after"]["cost_per_qualified_meeting_usd"] == 224
    assert study["evidence"]["permission_reference"] == "SYNTHETIC: no publication permission"
    assert proof["publishable"] is False
    assert study["results"]["publishable"] is False
    assert proof["benchmark_context"]["publishable"] is False


@pytest.mark.parametrize("vertical", VERTICAL_KITS)
def test_complete_internal_sales_package(vertical: str) -> None:
    proof = build_sales_proof(vertical)
    assert proof["case_study"] is None
    assert proof["proof_assets"]
    assert proof["review_gates"]
    assert proof["pilot_acceptance"]["qualified_meeting_checklist"]
    draft = build_vertical_drafts(vertical)
    body = draft.lead_magnet.content_data["body"]
    assert all(rule in body for rule in SHARED_RULES)
    assert all(asset in body for asset in proof["proof_assets"])


@pytest.mark.parametrize("count", [True, 1.5, "100", -1])
def test_untrusted_counts_are_rejected(count: object) -> None:
    data = json.loads(FIXTURE.read_text())
    data["before"]["attempts"] = count
    with pytest.raises(ValueError):
        CaseStudyEvidence.model_validate_json(json.dumps(data))


def test_unknown_evidence_fields_cannot_authorize_publication() -> None:
    data = json.loads(FIXTURE.read_text())
    data["publishable"] = True
    with pytest.raises(ValueError):
        CaseStudyEvidence.model_validate_json(json.dumps(data))


@pytest.mark.parametrize(
    "field,value",
    [
        ("source", " synthetic-before-not-evidence "),
        ("starts_at", "2026-01-15"),
        ("total_cost_usd", "NaN"),
        ("label", "   "),
        ("shown", 21),
        ("unknown", True),
    ],
)
def test_invalid_period_evidence_is_rejected(field: str, value: object) -> None:
    data = json.loads(FIXTURE.read_text())
    data["after"][field] = value
    with pytest.raises(ValueError):
        evidence = CaseStudyEvidence.model_validate_json(json.dumps(data))
        build_sales_proof("roofing", evidence)


def test_cli_exports_measured_draft() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.ops.export_vertical_drafts",
            "roofing",
            "--evidence",
            str(FIXTURE),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    exported = json.loads(result.stdout)
    assert exported["offer"]["is_active"] is False
    assert exported["lead_magnet"]["is_active"] is False
    assert (
        exported["sales_proof"]["case_study"]["results"]["after"]["cost_per_qualified_meeting_usd"]
        == "224"
    )


def test_cli_rejects_bad_evidence_without_echoing_it(tmp_path: Path) -> None:
    private = tmp_path / "evidence.json"
    private.write_text('{"private": "DO-NOT-PRINT"}')
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.ops.export_vertical_drafts",
            "hvac",
            "--evidence",
            str(private),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "Invalid evidence" in result.stderr
    assert "DO-NOT-PRINT" not in result.stderr
