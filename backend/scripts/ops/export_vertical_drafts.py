"""Export inactive offer/lead-magnet drafts and campaign copy for review.

Usage: uv run python -m scripts.ops.export_vertical_drafts real_estate
"""

import argparse
import json

from app.services.offers.vertical_drafts import build_vertical_drafts
from app.services.offers.vertical_kits import VERTICAL_KITS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vertical", choices=sorted(VERTICAL_KITS))
    args = parser.parse_args()
    drafts = build_vertical_drafts(args.vertical)
    print(
        json.dumps(
            {
                "offer": drafts.offer.model_dump(mode="json"),
                "lead_magnet": drafts.lead_magnet.model_dump(mode="json"),
                "campaign_copy": drafts.campaign_copy,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
