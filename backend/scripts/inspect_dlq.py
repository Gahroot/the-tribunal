#!/usr/bin/env python3
"""Inspect and replay rows in the ``failed_jobs`` dead-letter queue.

Subcommands:

    list                 Show recent DLQ rows, newest first.
    show <id>            Print one row in full (payload + error).
    replay <id>          Mark a row as ``retried`` (records intent — the
                         actual replay is the operator's responsibility,
                         since each worker owns its own retry mechanics).
    abandon <id>         Mark a row as ``abandoned`` so it stops showing
                         up in ``list --status pending`` triage views.
    purge --status ...   Delete rows in a terminal status (use sparingly).

Examples:

    uv run python scripts/inspect_dlq.py list
    uv run python scripts/inspect_dlq.py list --worker nudge_worker --status pending
    uv run python scripts/inspect_dlq.py show 7a4f...c1
    uv run python scripts/inspect_dlq.py replay 7a4f...c1
    uv run python scripts/inspect_dlq.py abandon 7a4f...c1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Make ``app`` importable when run as a plain script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.failed_job import (
    FAILED_JOB_STATUS_ABANDONED,
    FAILED_JOB_STATUS_PENDING,
    FAILED_JOB_STATUS_RETRIED,
    FAILED_JOB_STATUSES,
    FailedJob,
)


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "-"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%SZ")


def _short_id(row_id: uuid.UUID) -> str:
    return str(row_id).split("-", 1)[0]


async def _load(session: AsyncSession, row_id: str) -> FailedJob | None:
    try:
        parsed = uuid.UUID(row_id)
    except ValueError:
        print(f"error: not a valid UUID: {row_id!r}", file=sys.stderr)
        return None
    return await session.get(FailedJob, parsed)


async def cmd_list(args: argparse.Namespace) -> int:
    async with AsyncSessionLocal() as session:
        query = select(FailedJob).order_by(desc(FailedJob.last_failed_at))
        if args.status:
            query = query.where(FailedJob.status == args.status)
        if args.worker:
            query = query.where(FailedJob.worker_name == args.worker)
        query = query.limit(args.limit)
        rows = (await session.execute(query)).scalars().all()

    if not rows:
        print("No DLQ rows match the filters.")
        return 0

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "id": str(r.id),
                        "worker_name": r.worker_name,
                        "item_key": r.item_key,
                        "status": r.status,
                        "attempts": r.attempts,
                        "first_failed_at": _fmt_dt(r.first_failed_at),
                        "last_failed_at": _fmt_dt(r.last_failed_at),
                        "error": r.error,
                    }
                    for r in rows
                ],
                indent=2,
            )
        )
        return 0

    header = (
        f"{'id':<10} {'worker':<28} {'item_key':<28} "
        f"{'status':<10} {'att':>4} {'last_failed_at':<20}  error"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        error_snippet = (row.error or "").splitlines()[0][:80] if row.error else ""
        print(
            f"{_short_id(row.id):<10} "
            f"{row.worker_name[:28]:<28} "
            f"{row.item_key[:28]:<28} "
            f"{row.status:<10} "
            f"{row.attempts:>4} "
            f"{_fmt_dt(row.last_failed_at):<20}  "
            f"{error_snippet}"
        )
    return 0


async def cmd_show(args: argparse.Namespace) -> int:
    async with AsyncSessionLocal() as session:
        row = await _load(session, args.id)
        if row is None:
            print(f"No DLQ row with id {args.id}", file=sys.stderr)
            return 1
        out = {
            "id": str(row.id),
            "worker_name": row.worker_name,
            "item_key": row.item_key,
            "status": row.status,
            "attempts": row.attempts,
            "first_failed_at": _fmt_dt(row.first_failed_at),
            "last_failed_at": _fmt_dt(row.last_failed_at),
            "error": row.error,
            "payload": row.payload,
        }
        print(json.dumps(out, indent=2, default=str))
    return 0


async def _set_status(row_id: str, new_status: str) -> int:
    async with AsyncSessionLocal() as session:
        row = await _load(session, row_id)
        if row is None:
            print(f"No DLQ row with id {row_id}", file=sys.stderr)
            return 1
        row.status = new_status
        await session.commit()
        print(f"{_short_id(row.id)} -> {new_status}")
    return 0


async def cmd_replay(args: argparse.Namespace) -> int:
    # We don't actually re-invoke the worker function here — args/kwargs in
    # the payload may include live sessions/services that can't be revived
    # cross-process. Marking the row as "retried" records the operator's
    # intent; the worker that owns the item is responsible for re-enqueueing.
    return await _set_status(args.id, FAILED_JOB_STATUS_RETRIED)


async def cmd_abandon(args: argparse.Namespace) -> int:
    return await _set_status(args.id, FAILED_JOB_STATUS_ABANDONED)


async def cmd_purge(args: argparse.Namespace) -> int:
    if args.status == FAILED_JOB_STATUS_PENDING and not args.force:
        print(
            "Refusing to purge pending rows without --force "
            "(pending rows usually still need triage).",
            file=sys.stderr,
        )
        return 2
    async with AsyncSessionLocal() as session:
        result = await session.execute(delete(FailedJob).where(FailedJob.status == args.status))
        await session.commit()
        deleted = int(getattr(result, "rowcount", 0) or 0)
    print(f"Deleted {deleted} rows with status={args.status}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and replay rows in the failed_jobs DLQ.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List recent DLQ rows.")
    p_list.add_argument("--status", choices=FAILED_JOB_STATUSES, default=None)
    p_list.add_argument("--worker", help="Filter by worker_name.")
    p_list.add_argument("--limit", type=int, default=50)
    p_list.add_argument("--json", action="store_true", help="Emit JSON.")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="Show one DLQ row in full.")
    p_show.add_argument("id")
    p_show.set_defaults(func=cmd_show)

    p_replay = sub.add_parser("replay", help="Mark a row as retried (operator records intent).")
    p_replay.add_argument("id")
    p_replay.set_defaults(func=cmd_replay)

    p_abandon = sub.add_parser("abandon", help="Mark a row as abandoned.")
    p_abandon.add_argument("id")
    p_abandon.set_defaults(func=cmd_abandon)

    p_purge = sub.add_parser("purge", help="Delete rows in a given terminal status.")
    p_purge.add_argument("--status", choices=FAILED_JOB_STATUSES, required=True)
    p_purge.add_argument(
        "--force",
        action="store_true",
        help="Required to purge status=pending.",
    )
    p_purge.set_defaults(func=cmd_purge)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    exit_code: int = asyncio.run(args.func(args))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
