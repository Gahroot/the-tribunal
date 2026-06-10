"""Tests for ``app.services.telephony.inbound_screening``.

Pins the inbound caller spam-screening contract:

- Global opt-out callers are rejected.
- Explicit blocklist numbers are rejected.
- Operator-blocked conversations are rejected.
- Reputation labels map to reject (spam) / challenge (suspect).
- A burst of recent inbound calls degrades to low-priority handling.
- Clean callers (and disabled screening) are allowed.
- Screening is fail-open: an internal error yields ``allow``.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.telephony.inbound_screening import (
    InboundCallScreener,
    SpamDecision,
)


class _Result:
    def __init__(self, *, scalar: Any = None, count: Any = None) -> None:
        self._scalar = scalar
        self._count = count

    def scalar_one_or_none(self) -> Any:
        return self._scalar

    def scalar(self) -> Any:
        return self._count


def _make_workspace(settings: dict[str, Any] | None = None) -> MagicMock:
    ws = MagicMock()
    ws.settings = settings or {}
    return ws


def _make_db(workspace: Any, execute_returns: list[Any] | None = None) -> MagicMock:
    db = MagicMock()
    db.get = AsyncMock(return_value=workspace)
    db.execute = AsyncMock(side_effect=list(execute_returns or []))
    return db


def _screener(opt_out: bool = False) -> InboundCallScreener:
    manager = MagicMock()
    manager.check_opt_out = AsyncMock(return_value=opt_out)
    return InboundCallScreener(opt_out_manager=manager)


WORKSPACE_ID = uuid.uuid4()
CALLER = "+14155552672"


async def test_opt_out_caller_is_rejected() -> None:
    db = _make_db(_make_workspace())
    screener = _screener(opt_out=True)

    outcome = await screener.screen(db, WORKSPACE_ID, CALLER)

    assert outcome.decision is SpamDecision.REJECT
    assert outcome.reason == "global_opt_out"
    assert outcome.is_rejected


async def test_blocklisted_number_is_rejected() -> None:
    ws = _make_workspace({"inbound_screening": {"blocklist": [CALLER]}})
    db = _make_db(ws)
    screener = _screener(opt_out=False)

    outcome = await screener.screen(db, WORKSPACE_ID, CALLER)

    assert outcome.decision is SpamDecision.REJECT
    assert outcome.reason == "blocklist"


async def test_operator_blocked_conversation_is_rejected() -> None:
    ws = _make_workspace()
    # _is_conversation_blocked SELECT returns a conversation id.
    db = _make_db(ws, execute_returns=[_Result(scalar=uuid.uuid4())])
    screener = _screener(opt_out=False)

    outcome = await screener.screen(db, WORKSPACE_ID, CALLER)

    assert outcome.decision is SpamDecision.REJECT
    assert outcome.reason == "conversation_blocked"


async def test_reputation_spam_label_is_rejected() -> None:
    ws = _make_workspace({"inbound_screening": {"reputation": {CALLER: "spam"}}})
    # conversation-blocked check runs first and misses.
    db = _make_db(ws, execute_returns=[_Result(scalar=None)])
    screener = _screener(opt_out=False)

    outcome = await screener.screen(db, WORKSPACE_ID, CALLER)

    assert outcome.decision is SpamDecision.REJECT
    assert outcome.reason == "reputation_spam"


async def test_reputation_suspect_label_is_challenged() -> None:
    ws = _make_workspace({"inbound_screening": {"reputation": {CALLER: "suspect"}}})
    db = _make_db(ws, execute_returns=[_Result(scalar=None)])
    screener = _screener(opt_out=False)

    outcome = await screener.screen(db, WORKSPACE_ID, CALLER)

    assert outcome.decision is SpamDecision.CHALLENGE
    assert outcome.reason == "reputation_suspect"
    assert outcome.needs_challenge


async def test_call_burst_is_low_priority() -> None:
    ws = _make_workspace({"inbound_screening": {"burst_threshold": 3, "burst_window_minutes": 30}})
    db = _make_db(
        ws,
        execute_returns=[
            _Result(scalar=None),  # conversation-blocked miss
            _Result(count=5),  # recent inbound call count
        ],
    )
    screener = _screener(opt_out=False)

    outcome = await screener.screen(db, WORKSPACE_ID, CALLER)

    assert outcome.decision is SpamDecision.LOW_PRIORITY
    assert outcome.reason == "high_call_volume"
    assert outcome.details["recent_calls"] == 5
    assert outcome.is_low_priority


async def test_clean_caller_is_allowed() -> None:
    ws = _make_workspace()
    db = _make_db(
        ws,
        execute_returns=[
            _Result(scalar=None),  # conversation-blocked miss
            _Result(count=0),  # no recent calls
        ],
    )
    screener = _screener(opt_out=False)

    outcome = await screener.screen(db, WORKSPACE_ID, CALLER)

    assert outcome.decision is SpamDecision.ALLOW


async def test_disabled_screening_allows_everything() -> None:
    ws = _make_workspace({"inbound_screening": {"enabled": False}})
    db = _make_db(ws)
    # opt-out would reject if checked, but disabled screening short-circuits.
    screener = _screener(opt_out=True)

    outcome = await screener.screen(db, WORKSPACE_ID, CALLER)

    assert outcome.decision is SpamDecision.ALLOW
    assert outcome.reason == "screening_disabled"


async def test_screening_fails_open_on_error() -> None:
    ws = _make_workspace()
    db = _make_db(ws)
    db.get = AsyncMock(side_effect=RuntimeError("db down"))
    screener = _screener(opt_out=False)

    outcome = await screener.screen(db, WORKSPACE_ID, CALLER)

    assert outcome.decision is SpamDecision.ALLOW
    assert outcome.reason == "screening_error"


@pytest.mark.parametrize("blank", ["", None])
async def test_missing_caller_number_is_allowed(blank: Any) -> None:
    ws = _make_workspace()
    db = _make_db(ws, execute_returns=[_Result(scalar=None), _Result(count=0)])
    screener = _screener(opt_out=False)

    outcome = await screener.screen(db, WORKSPACE_ID, blank or "")

    assert outcome.decision is SpamDecision.ALLOW
