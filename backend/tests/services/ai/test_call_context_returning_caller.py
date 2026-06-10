"""Tests for returning-caller injection into call context.

Pins that :func:`app.services.ai.call_context._attach_returning_caller_context`
threads a returning-caller recap into ``contact_info['returning_summary']`` when
the caller is recognized, records a compact signal on ``context.metadata``, and
never raises (recognition must never break taking a call).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.services.ai.call_context import CallContext, _attach_returning_caller_context
from app.services.ai.caller_memory_service import CallerMemoryEntry, ReturningCallerInfo

WORKSPACE_ID = uuid.uuid4()
CONTACT_ID = 99


@pytest.mark.asyncio
async def test_injects_summary_for_returning_caller() -> None:
    context = CallContext(timezone="America/New_York")
    context.contact_info = {"name": "Sam"}

    info = ReturningCallerInfo(
        is_returning=True,
        prior_call_count=2,
        last_interaction_at=datetime(2026, 6, 1, tzinfo=UTC),
        memories=[
            CallerMemoryEntry(
                summary="Wanted a quote.", occurred_at=datetime(2026, 6, 1, tzinfo=UTC)
            )
        ],
    )
    with patch(
        "app.services.ai.caller_memory_service.detect_returning_caller",
        new=AsyncMock(return_value=info),
    ):
        await _attach_returning_caller_context(
            db=object(),
            context=context,
            workspace_id=WORKSPACE_ID,
            contact_id=CONTACT_ID,
            current_message_id=uuid.uuid4(),
            log=_StubLog(),
        )

    assert "returning_summary" in context.contact_info
    assert "Returning Caller" in context.contact_info["returning_summary"]
    assert context.metadata["returning_caller"]["is_returning"] is True
    assert context.metadata["returning_caller"]["prior_call_count"] == 2


@pytest.mark.asyncio
async def test_no_injection_for_new_caller() -> None:
    context = CallContext()
    context.contact_info = {"name": "New Person"}

    with patch(
        "app.services.ai.caller_memory_service.detect_returning_caller",
        new=AsyncMock(return_value=ReturningCallerInfo(is_returning=False)),
    ):
        await _attach_returning_caller_context(
            db=object(),
            context=context,
            workspace_id=WORKSPACE_ID,
            contact_id=CONTACT_ID,
            current_message_id=uuid.uuid4(),
            log=_StubLog(),
        )

    assert "returning_summary" not in context.contact_info
    assert "returning_caller" not in context.metadata


@pytest.mark.asyncio
async def test_detection_failure_is_swallowed() -> None:
    context = CallContext()
    context.contact_info = {"name": "Sam"}

    with patch(
        "app.services.ai.caller_memory_service.detect_returning_caller",
        new=AsyncMock(side_effect=RuntimeError("db down")),
    ):
        # Must not raise.
        await _attach_returning_caller_context(
            db=object(),
            context=context,
            workspace_id=WORKSPACE_ID,
            contact_id=CONTACT_ID,
            current_message_id=uuid.uuid4(),
            log=_StubLog(),
        )

    assert "returning_summary" not in context.contact_info


class _StubLog:
    def info(self, *_a: object, **_k: object) -> None: ...
    def warning(self, *_a: object, **_k: object) -> None: ...
