#!/usr/bin/env python3
"""Backfill script for PromptVersionStats.

Usage:
    python scripts/backfill_prompt_stats.py [--days=30] [--start=2025-01-01]

Options:
    --days      Number of days to backfill (default: 30)
    --start     Start date in YYYY-MM-DD format
    --end       End date in YYYY-MM-DD format (default: yesterday)
"""

import argparse
import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.workers.prompt_stats_worker import PromptStatsWorker


async def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill PromptVersionStats")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to backfill (default: 30)",
    )
    parser.add_argument(
        "--start",
        type=str,
        help="Start date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--end",
        type=str,
        help="End date in YYYY-MM-DD format (default: yesterday)",
    )

    args = parser.parse_args()

    # Determine date range
    if args.start:
        start_date = date.fromisoformat(args.start)
    else:
        start_date = date.today() - timedelta(days=args.days)

    if args.end:
        end_date = date.fromisoformat(args.end)
    else:
        end_date = date.today() - timedelta(days=1)

    print(f"Backfilling stats from {start_date} to {end_date}")

    worker = PromptStatsWorker()
    total = await worker.backfill(start_date, end_date)

    print(f"Backfill complete. Processed {total} version-date combinations.")


if __name__ == "__main__":
    asyncio.run(main())
