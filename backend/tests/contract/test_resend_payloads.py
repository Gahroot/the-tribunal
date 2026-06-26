"""Contract tests for Resend webhook payloads.

For each fixture under ``tests/contract/fixtures/resend/``:

1. Serialize the fixture to bytes.
2. Sign the body with a fresh Svix ``whsec_`` secret and patch
   ``settings.resend_webhook_secret`` to match.
3. POST to ``/webhooks/resend`` under a FastAPI test app.
4. Assert ``200 {"status": "ok"}`` and that ``handle_event`` was invoked
   with the verified event plus the ``svix-id`` as the idempotency key.

The downstream event processing — campaign counters, message status
transitions, ``EmailEvent`` row creation — is covered in
``tests/api/test_resend_handlers.py``. Here we pin the wire-format
contract for the four event types we care about plus the Svix
signature stack.
"""

from __future__ import annotations

import dataclasses
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.api.webhooks import resend as resend_router_module
from app.api.webhooks.resend import router as resend_router
from app.core.config import settings as app_settings
from app.services.webhooks.pipeline import (
    WebhookDispatchResult,
    WebhookIdempotencyDecision,
)
from app.services.webhooks.resend import ResendWebhookEvent
from tests.contract._helpers import (
    ResendSigner,
    build_app,
    encode_body,
    http_client,
)
from tests.contract.fixtures import load_fixture

# --------------------------------------------------------------------------- #
# Plumbing
# --------------------------------------------------------------------------- #


@pytest.fixture
def stub_dispatch(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Stub the Resend pipeline's domain dispatcher with an ``AsyncMock`` recorder.

    The router runs verification and parsing through a module-level
    ``WebhookPipeline`` (a frozen dataclass that captured its collaborators at
    import time), so we swap in a replacement pipeline that keeps the real
    verifier + parser — the wire-format contract under test — but short-circuits
    the idempotency check and records the dispatch call. Overriding the
    idempotency checker is required because the contract app injects an
    ``AsyncMock`` DB whose ``scalar_one_or_none()`` would otherwise look like an
    already-processed event and skip dispatch.
    """
    mock = AsyncMock(return_value=WebhookDispatchResult.processed())

    async def _always_process(*_args: Any, **_kwargs: Any) -> WebhookIdempotencyDecision:
        return WebhookIdempotencyDecision.process()

    patched_pipeline = dataclasses.replace(
        resend_router_module._RESEND_PIPELINE,
        idempotency_checker=_always_process,
        dispatcher=mock,
    )
    monkeypatch.setattr(resend_router_module, "_RESEND_PIPELINE", patched_pipeline)
    return mock


async def _post_signed(
    *, fixture: dict[str, Any], signer: ResendSigner
) -> tuple[int, dict[str, Any]]:
    """Sign *fixture* with *signer* and POST to /webhooks/resend."""
    app = build_app(resend_router, prefix="/webhooks/resend")
    body = encode_body(fixture)
    headers = {"content-type": "application/json", **signer.sign(body)}

    with patch.object(app_settings, "resend_webhook_secret", signer.secret):
        async with http_client(app) as client:
            response = await client.post("/webhooks/resend", content=body, headers=headers)

    return response.status_code, response.json()


def _assert_dispatch_called_with(
    dispatch: AsyncMock, *, expected_type: str, expected_email_id: str, msg_id: str
) -> ResendWebhookEvent:
    """Common assertion: ``dispatch_resend_event(db, event, log)``.

    The parser turns the verified payload into a ``ResendWebhookEvent`` DTO and
    the svix-id flows through as ``provider_event_id`` on that DTO.
    """
    dispatch.assert_awaited_once()
    call = dispatch.await_args
    # call.args == (db, event, log)
    event = call.args[1]
    assert isinstance(event, ResendWebhookEvent)
    assert event.event_type == expected_type
    assert event.data["email_id"] == expected_email_id
    assert event.provider_event_id == msg_id
    return event


# --------------------------------------------------------------------------- #
# Each event type → 200 + dispatch
# --------------------------------------------------------------------------- #


async def test_email_sent_payload_dispatches_to_handle_event(
    resend_signer: ResendSigner, stub_dispatch: AsyncMock
) -> None:
    fixture = load_fixture("resend", "email_sent.json")
    assert fixture["type"] == "email.sent"

    status, body = await _post_signed(fixture=fixture, signer=resend_signer)

    assert status == 200
    assert body == {"status": "ok"}
    event = _assert_dispatch_called_with(
        stub_dispatch,
        expected_type="email.sent",
        expected_email_id="ae2014de-c168-4c61-8267-contract0001",
        msg_id=resend_signer.msg_id,
    )
    # Contract: ``data.to`` is a list — the handler relies on iterable shape.
    assert isinstance(event.data["to"], list)
    assert event.data["to"] == ["client@example.com"]


async def test_email_delivered_payload_dispatches_to_handle_event(
    resend_signer: ResendSigner, stub_dispatch: AsyncMock
) -> None:
    fixture = load_fixture("resend", "email_delivered.json")
    assert fixture["type"] == "email.delivered"

    status, body = await _post_signed(fixture=fixture, signer=resend_signer)

    assert status == 200
    assert body == {"status": "ok"}
    _assert_dispatch_called_with(
        stub_dispatch,
        expected_type="email.delivered",
        expected_email_id="ae2014de-c168-4c61-8267-contract0001",
        msg_id=resend_signer.msg_id,
    )


async def test_email_bounced_payload_carries_bounce_metadata(
    resend_signer: ResendSigner, stub_dispatch: AsyncMock
) -> None:
    """A bounce event must include the ``bounce`` block the handler stores."""
    fixture = load_fixture("resend", "email_bounced.json")
    assert fixture["type"] == "email.bounced"

    status, body = await _post_signed(fixture=fixture, signer=resend_signer)

    assert status == 200
    assert body == {"status": "ok"}
    event = _assert_dispatch_called_with(
        stub_dispatch,
        expected_type="email.bounced",
        expected_email_id="ae2014de-c168-4c61-8267-contract0002",
        msg_id=resend_signer.msg_id,
    )
    bounce = event.data["bounce"]
    assert bounce["type"] == "Permanent"
    assert bounce["subType"] == "General"
    assert "hard bounce" in bounce["message"]


async def test_email_opened_payload_dispatches_to_handle_event(
    resend_signer: ResendSigner, stub_dispatch: AsyncMock
) -> None:
    fixture = load_fixture("resend", "email_opened.json")
    assert fixture["type"] == "email.opened"

    status, body = await _post_signed(fixture=fixture, signer=resend_signer)

    assert status == 200
    assert body == {"status": "ok"}
    _assert_dispatch_called_with(
        stub_dispatch,
        expected_type="email.opened",
        expected_email_id="ae2014de-c168-4c61-8267-contract0001",
        msg_id=resend_signer.msg_id,
    )


# --------------------------------------------------------------------------- #
# Signature stack — negative cases
# --------------------------------------------------------------------------- #


async def test_unsigned_resend_request_returns_400(
    resend_signer: ResendSigner, stub_dispatch: AsyncMock
) -> None:
    """No Svix headers → Svix verification raises → 400, no dispatch."""
    fixture = load_fixture("resend", "email_delivered.json")
    body = encode_body(fixture)
    app = build_app(resend_router, prefix="/webhooks/resend")

    with patch.object(app_settings, "resend_webhook_secret", resend_signer.secret):
        async with http_client(app) as client:
            response = await client.post(
                "/webhooks/resend",
                content=body,
                headers={"content-type": "application/json"},
            )

    assert response.status_code == 400
    stub_dispatch.assert_not_called()


async def test_tampered_resend_body_is_rejected(
    resend_signer: ResendSigner, stub_dispatch: AsyncMock
) -> None:
    """Body changed after signing → Svix HMAC mismatch → 400, no dispatch."""
    fixture = load_fixture("resend", "email_delivered.json")
    body_signed = encode_body(fixture)
    headers = {"content-type": "application/json", **resend_signer.sign(body_signed)}
    # Send a different body than the one we signed.
    body_sent = encode_body({**fixture, "type": "email.bounced"})

    app = build_app(resend_router, prefix="/webhooks/resend")
    with patch.object(app_settings, "resend_webhook_secret", resend_signer.secret):
        async with http_client(app) as client:
            response = await client.post("/webhooks/resend", content=body_sent, headers=headers)

    assert response.status_code == 400
    stub_dispatch.assert_not_called()


async def test_missing_resend_secret_returns_503(
    resend_signer: ResendSigner, stub_dispatch: AsyncMock
) -> None:
    """No ``resend_webhook_secret`` configured → 503, no dispatch."""
    fixture = load_fixture("resend", "email_sent.json")
    body = encode_body(fixture)
    headers = {"content-type": "application/json", **resend_signer.sign(body)}
    app = build_app(resend_router, prefix="/webhooks/resend")

    with patch.object(app_settings, "resend_webhook_secret", ""):
        async with http_client(app) as client:
            response = await client.post("/webhooks/resend", content=body, headers=headers)

    assert response.status_code == 503
    stub_dispatch.assert_not_called()
