"""Tests for contact engagement score service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.contacts.engagement_score import (
    EVENT_WEIGHTS,
    WINDOW_DAYS,
    _message_weight,
    _recency_factor,
    record_engagement,
)


def _make_message(
    *,
    channel: str = "sms",
    direction: str = "inbound",
    duration_seconds: int | None = None,
    age_days: float = 0.0,
) -> Any:
    """Build a Message-shaped stub."""
    return SimpleNamespace(
        channel=channel,
        direction=direction,
        duration_seconds=duration_seconds,
        created_at=datetime.now(UTC) - timedelta(days=age_days),
    )


def _fake_db(contact: Any, messages: list[Any], outcomes: list[Any]) -> MagicMock:
    """Build a fake AsyncSession that returns the given rows."""
    db = MagicMock()
    db.get = AsyncMock(return_value=contact)

    calls = {"n": 0}

    async def execute(_stmt: Any) -> Any:
        result = MagicMock()
        scalars = MagicMock()
        # First execute = messages, second = outcomes.
        scalars.all.return_value = messages if calls["n"] == 0 else outcomes
        result.scalars.return_value = scalars
        calls["n"] += 1
        return result

    db.execute = AsyncMock(side_effect=execute)
    return db


class TestRecencyFactor:
    def test_now_returns_one(self) -> None:
        now = datetime.now(UTC)
        assert _recency_factor(now, now) == 1.0

    def test_full_window_returns_zero(self) -> None:
        now = datetime.now(UTC)
        event_at = now - timedelta(days=WINDOW_DAYS)
        assert _recency_factor(event_at, now) == 0.0

    def test_halfway_is_half(self) -> None:
        now = datetime.now(UTC)
        event_at = now - timedelta(days=WINDOW_DAYS / 2)
        assert _recency_factor(event_at, now) == pytest.approx(0.5, abs=1e-6)

    def test_past_window_is_zero(self) -> None:
        now = datetime.now(UTC)
        event_at = now - timedelta(days=WINDOW_DAYS * 2)
        assert _recency_factor(event_at, now) == 0.0


class TestMessageWeight:
    def test_sms_inbound_uses_sms_in_weight(self) -> None:
        assert _message_weight(_make_message(channel="sms", direction="inbound")) == (
            EVENT_WEIGHTS["sms_in"]
        )

    def test_sms_outbound_uses_sms_out_weight(self) -> None:
        assert _message_weight(_make_message(channel="sms", direction="outbound")) == (
            EVENT_WEIGHTS["sms_out"]
        )

    def test_long_call_counts_as_completed(self) -> None:
        msg = _make_message(channel="voice", direction="inbound", duration_seconds=120)
        assert _message_weight(msg) == EVENT_WEIGHTS["call_completed"]

    def test_short_call_counts_as_answered(self) -> None:
        msg = _make_message(channel="voice", direction="inbound", duration_seconds=5)
        assert _message_weight(msg) == EVENT_WEIGHTS["call_answered"]

    def test_zero_duration_call_is_zero(self) -> None:
        msg = _make_message(channel="voice", direction="inbound", duration_seconds=0)
        assert _message_weight(msg) == 0


@pytest.mark.asyncio
async def test_record_engagement_fresh_contact_gets_positive_score() -> None:
    contact = SimpleNamespace(id=1, engagement_score=0, last_engaged_at=None)
    db = _fake_db(contact, [], [])

    await record_engagement(db, 1, "sms_in")

    assert contact.engagement_score == EVENT_WEIGHTS["sms_in"]
    assert contact.last_engaged_at is not None


@pytest.mark.asyncio
async def test_record_engagement_accumulates_recent_events() -> None:
    contact = SimpleNamespace(id=1, engagement_score=0, last_engaged_at=None)
    messages = [
        _make_message(channel="sms", direction="inbound", age_days=0),
        _make_message(channel="sms", direction="inbound", age_days=0),
    ]
    db = _fake_db(contact, messages, [])

    await record_engagement(db, 1, "sms_in")

    # Two historical inbound SMS (fresh) + one live event = ~60, clamped to 60.
    assert contact.engagement_score >= 2 * EVENT_WEIGHTS["sms_in"]


@pytest.mark.asyncio
async def test_record_engagement_old_events_decay() -> None:
    contact_new = SimpleNamespace(id=1, engagement_score=0, last_engaged_at=None)
    contact_old = SimpleNamespace(id=2, engagement_score=0, last_engaged_at=None)

    fresh = [_make_message(channel="sms", direction="inbound", age_days=0)]
    old = [_make_message(channel="sms", direction="inbound", age_days=25)]

    db_new = _fake_db(contact_new, fresh, [])
    db_old = _fake_db(contact_old, old, [])

    await record_engagement(db_new, 1, "sms_out")
    await record_engagement(db_old, 2, "sms_out")

    assert contact_new.engagement_score > contact_old.engagement_score


@pytest.mark.asyncio
async def test_record_engagement_clamps_to_100() -> None:
    contact = SimpleNamespace(id=1, engagement_score=0, last_engaged_at=None)
    # 20 fresh inbound SMS = 400 weight, should clamp to 100.
    messages = [
        _make_message(channel="sms", direction="inbound", age_days=0) for _ in range(20)
    ]
    db = _fake_db(contact, messages, [])

    await record_engagement(db, 1, "sms_in")

    assert contact.engagement_score == 100


@pytest.mark.asyncio
async def test_record_engagement_missing_contact_is_noop() -> None:
    db = _fake_db(contact=None, messages=[], outcomes=[])
    # Should not raise.
    await record_engagement(db, 999, "sms_in")
