"""Tests for the reusable webhook processing pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.webhooks.pipeline import (
    WebhookDispatchResult,
    WebhookIdempotencyDecision,
    WebhookPipeline,
    WebhookRequestEnvelope,
)


@dataclass(frozen=True, slots=True)
class _Event:
    event_type: str
    event_id: str | None
    idempotency_key: str | None

    @property
    def provider(self) -> str:
        return "unit"


def _make_request() -> WebhookRequestEnvelope:
    return WebhookRequestEnvelope(
        provider="unit",
        raw_body=b'{"type":"unit.created"}',
        headers={"webhook-id": "evt_1"},
    )


@pytest.mark.asyncio
async def test_pipeline_verifies_parses_dedupes_dispatches_and_audits() -> None:
    verified_payload = {"type": "unit.created"}
    event = _Event(
        event_type="unit.created",
        event_id="evt_1",
        idempotency_key="evt_1",
    )
    verifier = AsyncMock(return_value=verified_payload)
    parser = MagicMock(return_value=event)
    idempotency_checker = AsyncMock(return_value=WebhookIdempotencyDecision.process())
    dispatcher = AsyncMock(return_value=WebhookDispatchResult.processed())
    audit_sink = AsyncMock()
    db = MagicMock()
    log = _make_log()
    request = _make_request()

    pipeline = WebhookPipeline[dict[str, Any], _Event](
        provider="unit",
        verifier=verifier,
        parser=parser,
        idempotency_checker=idempotency_checker,
        dispatcher=dispatcher,
        audit_sink=audit_sink,
    )

    result = await pipeline.process(db=db, request=request, log=log)

    assert result.provider == "unit"
    assert result.event_type == "unit.created"
    assert result.event_id == "evt_1"
    assert result.idempotency_key == "evt_1"
    assert result.status == "processed"
    assert result.response_body() == {"status": "ok"}
    verifier.assert_awaited_once_with(request)
    parser.assert_called_once_with(verified_payload, request)
    idempotency_checker.assert_awaited_once_with(db, event, log)
    dispatcher.assert_awaited_once_with(db, event, log)
    audit_sink.assert_awaited_once()


@pytest.mark.asyncio
async def test_pipeline_replay_skips_dispatch_and_returns_deduped_body() -> None:
    event = _Event(
        event_type="unit.created",
        event_id="evt_1",
        idempotency_key="evt_1",
    )
    dispatcher = AsyncMock(return_value=WebhookDispatchResult.processed())
    audit_sink = AsyncMock()
    pipeline = WebhookPipeline[dict[str, Any], _Event](
        provider="unit",
        verifier=AsyncMock(return_value={"type": "unit.created"}),
        parser=MagicMock(return_value=event),
        idempotency_checker=AsyncMock(
            return_value=WebhookIdempotencyDecision.duplicate("already_processed")
        ),
        dispatcher=dispatcher,
        audit_sink=audit_sink,
    )

    result = await pipeline.process(db=MagicMock(), request=_make_request(), log=_make_log())

    assert result.status == "duplicate"
    assert result.reason == "already_processed"
    assert result.response_body() == {
        "status": "ok",
        "deduped": "true",
        "reason": "already_processed",
    }
    dispatcher.assert_not_awaited()
    audit_sink.assert_awaited_once()


def _make_log() -> MagicMock:
    log = MagicMock()
    log.bind = MagicMock(return_value=log)
    return log
