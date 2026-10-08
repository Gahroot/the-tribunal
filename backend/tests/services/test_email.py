"""Tests for async Resend email delivery helpers."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.models.workspace import Workspace
from app.services import email


class _FakeResendEmails:
    def __init__(self) -> None:
        self.send_async = AsyncMock(return_value={"id": "email_123"})
        self.send = AsyncMock()


class _FakeResend:
    def __init__(self) -> None:
        self.api_key: str | None = None
        self.Emails = _FakeResendEmails()


@pytest.fixture
def fake_resend(monkeypatch: pytest.MonkeyPatch) -> _FakeResend:
    client = _FakeResend()
    monkeypatch.setattr(email, "RESEND_AVAILABLE", True)
    monkeypatch.setattr(email, "resend", client)
    monkeypatch.setattr(email.settings, "resend_api_key", "resend-key")
    monkeypatch.setattr(email.settings, "resend_from_name", "Tribunal")
    monkeypatch.setattr(email.settings, "resend_from_email", "noreply@example.com")
    return client


@pytest.mark.asyncio
async def test_send_uses_resend_async_client(fake_resend: _FakeResend) -> None:
    result = await email._send(
        {
            "from": "Tribunal <noreply@example.com>",
            "to": ["lead@example.com"],
            "subject": "Hello",
            "html": "<p>Hello</p>",
        }
    )

    assert result == {"id": "email_123"}
    assert fake_resend.api_key == "resend-key"
    fake_resend.Emails.send_async.assert_awaited_once_with(
        {
            "from": "Tribunal <noreply@example.com>",
            "to": ["lead@example.com"],
            "subject": "Hello",
            "html": "<p>Hello</p>",
        },
        None,
    )
    fake_resend.Emails.send.assert_not_called()


@pytest.mark.asyncio
async def test_send_returns_none_when_resend_async_client_fails(
    fake_resend: _FakeResend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = MagicMock()
    fake_resend.Emails.send_async.side_effect = RuntimeError("network down")
    monkeypatch.setattr(email, "logger", logger)

    result = await email._send({"to": ["lead@example.com"]})

    assert result is None
    fake_resend.Emails.send_async.assert_awaited_once_with({"to": ["lead@example.com"]}, None)
    logger.error.assert_called_once()


@pytest.mark.asyncio
async def test_invitation_email_uses_async_resend_path(fake_resend: _FakeResend) -> None:
    sent = await email.send_invitation_email(
        to_email="agent@example.com",
        workspace_name="Acme Realty",
        inviter_name="Nolan",
        invitation_url="https://app.example/invitations/abc",
        role="admin",
    )

    assert sent is True
    call = fake_resend.Emails.send_async.await_args
    assert call is not None
    args: tuple[dict[str, Any], ...] = call.args
    params = args[0]
    assert params["from"] == "Tribunal <noreply@example.com>"
    assert params["to"] == ["agent@example.com"]
    assert params["subject"] == "You've been invited to join Acme Realty"
    assert "https://app.example/invitations/abc" in params["html"]
    fake_resend.Emails.send.assert_not_called()


@pytest.mark.asyncio
async def test_invitation_email_passes_resend_idempotency_key(fake_resend: _FakeResend) -> None:
    key = uuid.uuid4()

    sent = await email.send_invitation_email(
        to_email="agent@example.com",
        workspace_name="Acme Realty",
        inviter_name="Nolan",
        invitation_url="https://app.example/invitations/abc",
        role="admin",
        idempotency_key=key,
    )

    assert sent is True
    fake_resend.Emails.send_async.assert_awaited_once()
    assert fake_resend.Emails.send_async.await_args.args[1] == {"idempotency_key": str(key)}


@pytest.mark.asyncio
async def test_brand_email_credentials_and_senders_are_isolated(monkeypatch):
    import asyncio
    import json

    from app.core.encryption import encrypt_json
    from app.models.workspace import WorkspaceIntegration

    brands = [uuid.uuid4(), uuid.uuid4()]
    records = {
        brand: WorkspaceIntegration(
            workspace_id=brand,
            integration_type="resend",
            is_active=True,
            encrypted_credentials=encrypt_json(
                {
                    "api_key": f"fixture-{index}",
                    "from_email": f"brand{index}@example.com",
                    "from_name": f"Brand {index}",
                }
            ),
        )
        for index, brand in enumerate(brands)
    }
    seen = []

    def handle(request):
        seen.append((request.headers["Authorization"], json.loads(request.content)))
        return httpx.Response(200, json={"id": "fixture-email"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        email.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    monkeypatch.setattr(email.settings, "resend_api_key", "")

    async def send(brand):
        db = AsyncMock()
        db.get.return_value = Workspace(
            id=brand,
            name="Workspace fallback",
            is_active=True,
            settings={"business_name": f"Business {brands.index(brand)} <&>"},
        )

        async def execute(statement):
            assert brand in statement.compile().params.values()
            return MagicMock(scalar_one_or_none=MagicMock(return_value=records[brand]))

        db.execute.side_effect = execute
        return await email.send_automation_email(
            "customer@example.com", "Subject", "Body", uuid.uuid4(), db=db, workspace_id=brand
        )

    assert all(await asyncio.gather(*(send(brand) for brand in brands)))
    assert {key for key, _ in seen} == {"Bearer fixture-0", "Bearer fixture-1"}
    for key, params in seen:
        index = key[-1]
        assert params["from"] == f"Brand {index} <brand{index}@example.com>"
        assert f"Sent by Business {index} &lt;&amp;&gt;" in params["html"]
        assert f"Sent by Business {index} <&>" in params["text"]
        assert f"Business {1 - int(index)}" not in params["html"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    [
        "disabled",
        "unreadable",
        "empty",
        "sender_missing",
        "rejected",
        "managed",
        "invalid_sender",
        "unsafe_sender",
        "unsafe_name",
    ],
)
async def test_brand_email_fails_closed_or_uses_permitted_managed_fallback(monkeypatch, state):
    from app.core.encryption import encrypt_json
    from app.models.workspace import WorkspaceIntegration

    brand = uuid.uuid4()
    values = {"api_key": "brand-fixture", "from_email": "brand@example.com"}
    if state == "empty":
        values["api_key"] = ""
    if state == "sender_missing":
        values.pop("from_email")
    if state == "invalid_sender":
        values["from_email"] = "not-an-email"
    if state == "unsafe_sender":
        values["from_email"] = "brand@example.com\r\n"
    if state == "unsafe_name":
        values["from_name"] = "Brand\nA"
    record = (
        None
        if state == "managed"
        else WorkspaceIntegration(
            workspace_id=brand,
            integration_type="resend",
            is_active=state != "disabled",
            encrypted_credentials="unreadable" if state == "unreadable" else encrypt_json(values),
        )
    )
    db = AsyncMock()
    db.get.return_value = Workspace(id=brand, name="Brand A", settings={}, is_active=True)
    db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=record))
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(401 if state == "rejected" else 200, json={"id": "fixture"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        email.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    monkeypatch.setattr(email.settings, "resend_api_key", "platform-fixture")
    monkeypatch.setattr(email.settings, "resend_from_email", "platform@example.org")
    result = await email._send(
        {"from": "platform@example.com", "to": ["customer@example.com"]}, db=db, workspace_id=brand
    )
    assert (result is not None) is (state == "managed")
    if state == "managed":
        import json

        assert seen[0].headers["Authorization"] == "Bearer platform-fixture"
        assert json.loads(seen[0].content)["from"] == (
            "Brand A via The Tribunal <platform@example.org>"
        )
    elif state == "rejected":
        assert len(seen) == 1
        assert seen[0].headers["Authorization"] == "Bearer brand-fixture"
    else:
        assert not seen


@pytest.mark.parametrize("managed", [False, True])
async def test_two_brand_lead_magnets_render_through_provider_fixture(monkeypatch, managed):
    import json
    from email.utils import parseaddr

    from tribunal_lead_capture.service import deliver_lead_magnet_to_lead

    from app.core.encryption import encrypt_json
    from app.models.lead_magnet import LeadMagnet
    from app.models.lead_magnet_lead import LeadMagnetLead
    from app.models.workspace import WorkspaceIntegration

    seen = []

    def handle(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "fixture"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        email.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    monkeypatch.setattr(email.settings, "resend_api_key", "platform-fixture")
    monkeypatch.setattr(email.settings, "resend_from_email", "platform@example.org")
    for label in ["Brand A", "Brand B"]:
        brand, magnet_id = uuid.uuid4(), uuid.uuid4()
        db = AsyncMock()
        db.get.return_value = Workspace(
            id=brand, name=label, settings={"business_name": ""}, is_active=True
        )
        record = (
            None
            if managed
            else WorkspaceIntegration(
                workspace_id=brand,
                integration_type="resend",
                is_active=True,
                encrypted_credentials=encrypt_json(
                    {
                        "api_key": "brand-fixture",
                        "from_email": "sender@example.org",
                    }
                ),
            )
        )

        async def execute(statement, brand=brand, record=record):
            assert brand in statement.compile().params.values()
            return MagicMock(scalar_one_or_none=MagicMock(return_value=record))

        db.execute.side_effect = execute
        lead = LeadMagnetLead(
            id=uuid.uuid4(),
            workspace_id=brand,
            lead_magnet_id=magnet_id,
            email="fixture@example.org",
            name="Pat",
        )
        magnet = LeadMagnet(
            id=magnet_id,
            workspace_id=brand,
            name="Guide <&>",
            content_url="https://example.org/guide.pdf",
        )
        assert await deliver_lead_magnet_to_lead(
            lead=lead,
            lead_magnet=magnet,
            offer_name="Offer",
            db=db,
            workspace_id=brand,
        )
        params = seen[-1]
        expected_name = f"{label} via The Tribunal" if managed else label
        expected_sender = "platform@example.org" if managed else "sender@example.org"
        assert parseaddr(params["from"]) == (expected_name, expected_sender)
        assert f"— {label}" in params["text"]
        assert f"Sent by {label}" in params["html"]
        assert "Guide &lt;&amp;&gt;" in params["html"]
        assert ("Brand B" if label == "Brand A" else "Brand A") not in params["html"]
        assert "— The Tribunal" not in params["text"]
        assert lead.delivered


@pytest.mark.parametrize("state", ["missing", "inactive", "invalid_name", "unverified"])
async def test_customer_identity_failure_never_uses_platform_send(monkeypatch, fake_resend, state):
    from app.services.integration_credentials import OutboundCredentials

    db = AsyncMock()
    db.get.return_value = (
        None
        if state == "missing"
        else Workspace(
            name="Brand A",
            is_active=state != "inactive",
            settings={"business_name": "Bad\nname" if state == "invalid_name" else "Brand A"},
        )
    )
    monkeypatch.setattr(
        email,
        "resolve_outbound_credentials",
        AsyncMock(
            return_value=OutboundCredentials(
                "fixture", "workspace", {"from_email": "brand@example.org"}
            )
        ),
    )
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(403, json={"message": "Sender domain is not verified"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        email.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    assert not await email.send_automation_email(
        "fixture@example.org",
        "Subject",
        "Body",
        db=db,
        workspace_id=uuid.uuid4(),
    )
    assert len(requests) == (1 if state == "unverified" else 0)
    fake_resend.Emails.send_async.assert_not_awaited()
