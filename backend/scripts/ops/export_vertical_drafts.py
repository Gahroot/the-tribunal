"""Export inactive offer/lead-magnet drafts and campaign copy for review.

Usage: uv run python -m scripts.ops.export_vertical_drafts real_estate
"""

import argparse
import json
from decimal import Decimal
from pathlib import Path

from pydantic import ValidationError

from app.services.offers.sales_proof import CaseStudyEvidence, build_sales_proof
from app.services.offers.vertical_drafts import build_vertical_drafts
from app.services.offers.vertical_kits import VERTICAL_KITS


def _json_decimal(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError("Unsupported export value")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vertical", choices=sorted(VERTICAL_KITS))
    parser.add_argument(
        "--evidence", type=Path, help="Private aggregate case-study JSON (max 64 KiB)"
    )
    args = parser.parse_args()
    evidence = None
    try:
        if args.evidence:
            with args.evidence.open("rb") as source:
                raw = source.read(65537)
            if len(raw) > 65536:
                raise ValueError("Evidence file exceeds 64 KiB")
            evidence = CaseStudyEvidence.model_validate_json(raw)
        proof = build_sales_proof(args.vertical, evidence)
    except (OSError, ValueError, ValidationError):
        # Do not echo source data or Pydantic errors containing private input values.
        parser.error("Invalid evidence: check file access, size, schema and comparison windows")
    drafts = build_vertical_drafts(args.vertical)
    print(
        json.dumps(
            {
                "offer": drafts.offer.model_dump(mode="json"),
                "lead_magnet": drafts.lead_magnet.model_dump(mode="json"),
                "campaign_copy": drafts.campaign_copy,
                "sales_proof": proof,
            },
            indent=2,
            default=_json_decimal,
        )
    )


if __name__ == "__main__":
    main()
