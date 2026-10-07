"""Integration tests for the nudge working list against a real database.

Run with ``-m integration``. Covers RF-018: a delivered (sent) nudge is still
open work, completed/dismissed nudges leave the working list, explicit status
filters keep history reachable, and snoozed nudges follow the worker's
existing expiry timing. Each test rolls back; nothing is committed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.nudges import dismiss_nudge, list_nudges
from app.db.session import AsyncSessionLocal, engine
from app.models.human_nudge import HumanNudge
from app.models.workspace import Workspace
from app.workers.nudge_worker import NudgeWorker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(autouse=True)
async def _fresh_engine_pool():
    """Dispose the shared engine pool around each test (loop-affinity safety)."""
    await engine.dispose()
    yield
    await engine.dispose()


async def _workspace(db: AsyncSession) -> Workspace:
    ws = Workspace(
        id=uuid.uuid4(),
        name="Nudge scope",
        slug=f"nudge-scope-{uuid.uuid4().hex[:8]}",
        settings={},
    )
    db.add(ws)
    await db.flush()
    return ws


def _nudge(ws: Workspace, title: str, status: str, **kw: object) -> HumanNudge:
    return HumanNudge(
        workspace_id=ws.id,
        contact_id=None,
        nudge_type="monitor_idle",
        title=title,
        message="m",
        due_date=datetime.now(UTC),
        status=status,
        dedup_key=f"test:{uuid.uuid4().hex}",
        **kw,
    )


async def _titles(db: AsyncSession, ws: Workspace, status: str | None) -> set[str]:
    page = await list_nudges(
        workspace=ws,
        db=db,
        status_filter=status,
        nudge_type=None,
        priority=None,
        contact_id=None,
        page=1,
        page_size=100,
    )
    assert page.total == len(page.items)
    return {item.title for item in page.items}


async def test_delivered_nudge_stays_in_active_work_until_resolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with AsyncSessionLocal() as db:
        ws = await _workspace(db)
        now = datetime.now(UTC)
        pending = _nudge(ws, "pending", "pending")
        sent = _nudge(ws, "sent", "sent", delivered_via="push", delivered_at=now)
        db.add_all(
            [
                pending,
                sent,
                _nudge(ws, "acted", "acted", acted_at=now),
                _nudge(ws, "dismissed", "dismissed"),
                _nudge(ws, "snoozed", "snoozed", snoozed_until=now + timedelta(days=1)),
            ]
        )
        await db.flush()

        assert await _titles(db, ws, None) == {"pending", "sent"}
        assert await _titles(db, ws, "active") == {"pending", "sent"}

        # Explicit filters still reach each status, including history.
        assert await _titles(db, ws, "sent") == {"sent"}
        assert await _titles(db, ws, "acted") == {"acted"}
        assert await _titles(db, ws, "dismissed") == {"dismissed"}
        assert await _titles(db, ws, "snoozed") == {"snoozed"}

        # Dismissing the delivered nudge removes it from active work.
        monkeypatch.setattr(db, "commit", db.flush)  # keep the test transactional
        await dismiss_nudge(workspace=ws, db=db, nudge_id=sent.id)
        assert await _titles(db, ws, None) == {"pending"}
        assert await _titles(db, ws, "dismissed") == {"dismissed", "sent"}
        await db.rollback()


async def test_snoozed_nudge_returns_to_active_work_after_snooze_ends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with AsyncSessionLocal() as db:
        ws = await _workspace(db)
        now = datetime.now(UTC)
        db.add_all(
            [
                _nudge(ws, "expired", "snoozed", snoozed_until=now - timedelta(minutes=1)),
                _nudge(ws, "future", "snoozed", snoozed_until=now + timedelta(days=1)),
            ]
        )
        await db.flush()
        assert await _titles(db, ws, None) == set()

        monkeypatch.setattr(db, "commit", db.flush)  # keep the test transactional
        await NudgeWorker()._expire_snoozed_nudges(db)

        assert await _titles(db, ws, None) == {"expired"}
        assert await _titles(db, ws, "snoozed") == {"future"}
        await db.rollback()
