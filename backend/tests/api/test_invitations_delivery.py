"""Invitation creation vs. email delivery (RF-017).

Creating an invitation and emailing it are separate outcomes: the API must
report the sender's real result, keep the invitation when delivery fails, and
let admins resend without creating duplicate pending invitations.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db
from app.api.v1 import invitations as invitations_module
from app.models.invitation import WorkspaceInvitation
from app.services import email as email_module

WS_ID = uuid.uuid4()
INVITE_EMAIL = "teammate@example.com"
BASE = f"/api/v1/workspaces/{WS_ID}/invitations"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


def _result(scalar: Any = None, scalars: list[Any] | None = None) -> MagicMock:
    res = MagicMock()
    res.scalar_one_or_none.return_value = scalar
    res.scalars.return_value.all.return_value = scalars or []
    return res


def _user() -> MagicMock:
    user = MagicMock()
    user.id = 7
    user.is_active = True
    user.email = "owner@example.com"
    user.full_name = "Olive Owner"
    return user


def _membership(role: str = "owner") -> MagicMock:
    membership = MagicMock()
    membership.role = role
    return membership


def _workspace() -> MagicMock:
    ws = MagicMock()
    ws.id = WS_ID
    ws.name = "Acme Realty"
    return ws


def _fill_defaults(obj: WorkspaceInvitation) -> None:
    """Emulate the DB applying column defaults on refresh."""
    obj.id = obj.id or uuid.uuid4()
    obj.token = obj.token or "secret-token-abc"
    obj.status = obj.status or "pending"
    obj.expires_at = obj.expires_at or datetime.now(UTC) + timedelta(days=7)
    obj.created_at = obj.created_at or datetime.now(UTC)
    obj.email_attempt_count = obj.email_attempt_count or 0


def _make_app(db: AsyncMock) -> FastAPI:
    app = FastAPI(lifespan=_lifespan)

    async def override_db() -> AsyncIterator[AsyncMock]:
        yield db

    async def override_user() -> MagicMock:
        return _user()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    app.include_router(invitations_module.router, prefix="/api/v1/workspaces/{workspace_id}/invitations")
    return app


def _make_db(*results: MagicMock) -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(side_effect=list(results))

    async def refresh(obj: WorkspaceInvitation) -> None:
        _fill_defaults(obj)

    db.refresh = AsyncMock(side_effect=refresh)
    return db


def _create_db(pending: list[Any] | None = None) -> AsyncMock:
    return _make_db(
        _result(_membership()),  # verify_workspace_admin
        _result(_workspace()),  # workspace lookup
        _result(None),  # existing user by email
        _result(scalars=pending or []),  # pending invitations
    )


def _resend_db(invitation: WorkspaceInvitation) -> AsyncMock:
    return _make_db(
        _result(_membership()),
        _result(invitation),
        _result(_workspace()),
    )


async def _post(app: FastAPI, path: str, json: dict[str, Any] | None = None) -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(path, json=json)


class _FakeResend:
    def __init__(self) -> None:
        self.api_key: str | None = None
        self.Emails = MagicMock()
        self.Emails.send_async = AsyncMock(return_value={"id": "email_123"})


@pytest.fixture
def email_configured(monkeypatch: pytest.MonkeyPatch) -> _FakeResend:
    client = _FakeResend()
    monkeypatch.setattr(email_module, "RESEND_AVAILABLE", True)
    monkeypatch.setattr(email_module, "resend", client)
    monkeypatch.setattr(email_module.settings, "resend_api_key", "resend-key")
    monkeypatch.setattr(email_module.settings, "frontend_url", "https://app.example")
    return client


@pytest.mark.asyncio
async def test_create_reports_sent_and_captures_real_email(email_configured: _FakeResend) -> None:
    db = _create_db()

    resp = await _post(_make_app(db), BASE, {"email": INVITE_EMAIL, "role": "admin"})

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    assert body["email_status"] == "sent"
    assert body["email_attempt_count"] == 1
    assert body["email_sent_at"] is not None
    assert "token" not in body
    assert "secret-token-abc" not in resp.text

    email_configured.Emails.send_async.assert_awaited_once()
    params = email_configured.Emails.send_async.await_args.args[0]
    assert params["to"] == [INVITE_EMAIL]
    assert "Acme Realty" in params["subject"]
    assert "Acme Realty" in params["html"]
    assert "an administrator" in params["html"]
    assert "https://app.example/invite/secret-token-abc" in params["html"]
    db.add.assert_called_once()


@pytest.mark.asyncio
async def test_create_keeps_invitation_but_reports_failed_when_sender_returns_false(
    email_configured: _FakeResend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(invitations_module, "send_invitation_email", AsyncMock(return_value=False))
    db = _create_db()

    resp = await _post(_make_app(db), BASE, {"email": INVITE_EMAIL})

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    assert body["email_status"] == "failed"
    assert body["email_sent_at"] is None
    db.add.assert_called_once()
    # Invitation committed before the send, delivery outcome committed after.
    assert db.commit.await_count == 2


@pytest.mark.asyncio
async def test_create_reports_failed_when_sender_raises(
    email_configured: _FakeResend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        invitations_module,
        "send_invitation_email",
        AsyncMock(side_effect=RuntimeError("provider exploded")),
    )
    db = _create_db()

    resp = await _post(_make_app(db), BASE, {"email": INVITE_EMAIL})

    assert resp.status_code == 201
    assert resp.json()["email_status"] == "failed"
    assert "provider exploded" not in resp.text


@pytest.mark.asyncio
async def test_create_reports_not_configured_without_attempting_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(email_module.settings, "resend_api_key", None)
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(invitations_module, "send_invitation_email", sender)
    db = _create_db()

    resp = await _post(_make_app(db), BASE, {"email": INVITE_EMAIL})

    assert resp.status_code == 201
    assert resp.json()["email_status"] == "not_configured"
    sender.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_rejects_duplicate_active_pending_invitation(
    email_configured: _FakeResend,
) -> None:
    existing = WorkspaceInvitation(
        workspace_id=WS_ID,
        email=INVITE_EMAIL,
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(days=3),
    )
    db = _create_db(pending=[existing])

    resp = await _post(_make_app(db), BASE, {"email": "Teammate@Example.com"})

    assert resp.status_code == 409
    assert "already pending" in resp.json()["detail"]
    db.add.assert_not_called()
    email_configured.Emails.send_async.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_supersedes_expired_pending_invitation(email_configured: _FakeResend) -> None:
    expired = WorkspaceInvitation(
        workspace_id=WS_ID,
        email=INVITE_EMAIL,
        status="pending",
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    db = _create_db(pending=[expired])

    resp = await _post(_make_app(db), BASE, {"email": INVITE_EMAIL})

    assert resp.status_code == 201
    assert expired.status == "expired"


@pytest.mark.asyncio
async def test_retry_after_failure_resends_same_invitation_without_duplicate(
    email_configured: _FakeResend, monkeypatch: pytest.MonkeyPatch
) -> None:
    sender = AsyncMock(return_value=False)
    monkeypatch.setattr(invitations_module, "send_invitation_email", sender)
    create_db = _create_db()
    created = await _post(_make_app(create_db), BASE, {"email": INVITE_EMAIL})
    assert created.json()["email_status"] == "failed"
    invitation: WorkspaceInvitation = create_db.add.call_args.args[0]

    sender.return_value = True
    resend_db = _resend_db(invitation)
    resp = await _post(_make_app(resend_db), f"{BASE}/{invitation.id}/resend")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(invitation.id)
    assert body["email_status"] == "sent"
    assert body["email_attempt_count"] == 2
    resend_db.add.assert_not_called()
    # Same link, distinct provider idempotency key per attempt.
    first, second = sender.await_args_list
    assert first.kwargs["invitation_url"] == second.kwargs["invitation_url"]
    assert first.kwargs["idempotency_key"] != second.kwargs["idempotency_key"]


@pytest.mark.asyncio
async def test_resend_of_expired_invitation_only_rotates_token_after_success(
    email_configured: _FakeResend, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_expiry = datetime.now(UTC) - timedelta(hours=1)
    invitation = WorkspaceInvitation(
        id=uuid.uuid4(),
        workspace_id=WS_ID,
        email=INVITE_EMAIL,
        role="member",
        status="pending",
        token="old-token",
        expires_at=old_expiry,
        created_at=datetime.now(UTC) - timedelta(days=8),
        email_attempt_count=1,
        email_status="failed",
    )
    sender = AsyncMock(return_value=False)
    monkeypatch.setattr(invitations_module, "send_invitation_email", sender)

    failed = await _post(_make_app(_resend_db(invitation)), f"{BASE}/{invitation.id}/resend")
    assert failed.json()["email_status"] == "failed"
    assert invitation.token == "old-token"
    assert invitation.expires_at == old_expiry

    sender.return_value = True
    sent = await _post(_make_app(_resend_db(invitation)), f"{BASE}/{invitation.id}/resend")
    assert sent.json()["email_status"] == "sent"
    assert sent.json()["is_expired"] is False
    assert invitation.token != "old-token"
    assert invitation.expires_at > datetime.now(UTC)
    assert invitation.token in sender.await_args.kwargs["invitation_url"]
    assert invitation.token not in sent.text


@pytest.mark.asyncio
async def test_resend_rejects_non_pending_invitation(email_configured: _FakeResend) -> None:
    invitation = WorkspaceInvitation(id=uuid.uuid4(), workspace_id=WS_ID, status="accepted")

    resp = await _post(_make_app(_resend_db(invitation)), f"{BASE}/{invitation.id}/resend")

    assert resp.status_code == 400
    email_configured.Emails.send_async.assert_not_awaited()


@pytest.mark.asyncio
async def test_resend_throttles_recently_sent_invitation(email_configured: _FakeResend) -> None:
    invitation = WorkspaceInvitation(
        id=uuid.uuid4(),
        workspace_id=WS_ID,
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(days=7),
        email_status="sent",
        email_last_attempt_at=datetime.now(UTC) - timedelta(seconds=5),
    )

    resp = await _post(_make_app(_resend_db(invitation)), f"{BASE}/{invitation.id}/resend")

    assert resp.status_code == 429
    email_configured.Emails.send_async.assert_not_awaited()


@pytest.mark.asyncio
async def test_resend_requires_admin(email_configured: _FakeResend) -> None:
    db = _make_db(_result(_membership("member")))

    resp = await _post(_make_app(db), f"{BASE}/{uuid.uuid4()}/resend")

    assert resp.status_code == 403
    email_configured.Emails.send_async.assert_not_awaited()
