#!/usr/bin/env python3
"""READ-ONLY audit of stored campaign ``sending_days`` encodings (RF-006).

The contract (``app/core/sending_days.py``) is Python ``weekday()``:
Monday=0 … Sunday=6. Until RF-006 the dashboard day picker used JavaScript
``getDay()`` values (Sunday=0), so a campaign created in the UI with
"Mon–Fri" was stored as ``[1, 2, 3, 4, 5]`` and the worker ran it Tue–Sat.
Rows written by backend defaults (onboarding/realtor template) already use
Monday=0, so the stored integers alone cannot tell which intent a row had.

This script never writes. It lists every SMS/voice campaign and message test
whose stored days would mean something different under the legacy UI
encoding, showing both readings, so an operator can make an explicit
migration decision per row. Do not bulk-rewrite these rows by guessing.

Examples:

    uv run python scripts/ops/audit_campaign_sending_days.py --env local
    uv run python scripts/ops/audit_campaign_sending_days.py --env local --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

# --- harness bootstrap: locate ``backend/`` so ``app`` + ``scripts`` import ----
_BACKEND_DIR = next(
    p / "backend"
    for p in Path(__file__).resolve().parents
    if (p / "backend" / "scripts" / "_harness.py").is_file()
)
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.sending_days import DAY_NAMES  # noqa: E402
from scripts._harness import (  # noqa: E402
    EXIT_OK,
    ExecutionContext,
    add_standard_arguments,
    from_args,
    log_event,
    run,
)

logger = logging.getLogger("sending_days_audit")


def legacy_ui_to_contract(days: Sequence[int]) -> list[int]:
    """Reinterpret pre-RF-006 UI values (Sunday=0) in the Monday=0 contract."""
    return sorted({(day - 1) % 7 for day in days})


def describe(days: Sequence[int]) -> str:
    return ", ".join(DAY_NAMES[d][:3] if 0 <= d <= 6 else f"?{d}" for d in sorted(set(days)))


def is_ambiguous(days: Sequence[int] | None) -> bool:
    """True when the two encodings yield different permitted days."""
    if not days:
        return False
    return sorted(set(days)) != legacy_ui_to_contract(days)


@dataclass(frozen=True, slots=True)
class Finding:
    table: str
    id: str
    workspace_id: str
    kind: str
    status: str
    created_at: str
    stored: list[int]
    as_contract: str
    if_legacy_ui: str


async def _collect() -> list[Finding]:
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.campaign import Campaign
    from app.models.message_test import MessageTest

    findings: list[Finding] = []
    async with AsyncSessionLocal() as session:
        campaigns = (
            await session.execute(select(Campaign).where(Campaign.sending_days.is_not(None)))
        ).scalars()
        for c in campaigns:
            if is_ambiguous(c.sending_days):
                findings.append(_finding("campaigns", c, str(c.campaign_type)))
        tests = (
            await session.execute(select(MessageTest).where(MessageTest.sending_days.is_not(None)))
        ).scalars()
        for t in tests:
            if is_ambiguous(t.sending_days):
                findings.append(_finding("message_tests", t, "message_test"))
    return findings


class _ScheduledRow(Protocol):
    @property
    def id(self) -> object: ...
    @property
    def workspace_id(self) -> object: ...
    @property
    def status(self) -> object: ...
    @property
    def created_at(self) -> datetime: ...
    @property
    def sending_days(self) -> list[int] | None: ...


def _finding(table: str, row: _ScheduledRow, kind: str) -> Finding:
    days = list(row.sending_days or [])
    return Finding(
        table=table,
        id=str(row.id),
        workspace_id=str(row.workspace_id),
        kind=kind,
        status=str(row.status),
        created_at=row.created_at.isoformat(),
        stored=days,
        as_contract=describe(days),
        if_legacy_ui=describe(legacy_ui_to_contract(days)),
    )


async def _main(args: argparse.Namespace, ctx: ExecutionContext) -> int:
    log_event(logger, logging.INFO, "auditing sending_days (read-only)", env=ctx.env.value)
    findings = await _collect()
    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        for f in findings:
            print(
                f"{f.table:<14} {f.id} ws={f.workspace_id} {f.kind:<18} {f.status:<10} "
                f"stored={f.stored} worker-runs=[{f.as_contract}] "
                f"if-created-in-old-UI=[{f.if_legacy_ui}]"
            )
    log_event(
        logger,
        logging.WARNING if findings else logging.INFO,
        "ambiguous rows need an explicit per-row migration decision; nothing was changed",
        ambiguous=len(findings),
    )
    return EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--json", action="store_true", help="Emit findings as JSON.")
    add_standard_arguments(parser, writes=False, default_env=None)
    args = parser.parse_args()
    ctx = from_args(args, logger_name="sending_days_audit")
    return int(asyncio.run(_main(args, ctx)))


if __name__ == "__main__":
    raise SystemExit(run(main))
