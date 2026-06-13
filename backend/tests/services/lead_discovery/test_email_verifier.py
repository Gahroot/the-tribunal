"""Tests for the config-gated email verifier.

The default (disabled) tier must never do I/O and must always return a verdict —
the reveal flow relies on it never raising.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.lead_discovery.email_verifier import (
    EmailVerificationStatus,
    verify_email,
)


@pytest.mark.asyncio
async def test_disabled_returns_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "email_verification_enabled", False)
    result = await verify_email("jane@acme.com")
    assert result.status == EmailVerificationStatus.UNKNOWN
    assert result.checked_mx is False
    assert result.checked_smtp is False


@pytest.mark.asyncio
async def test_malformed_email_is_undeliverable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "email_verification_enabled", True)
    result = await verify_email("not-an-email")
    assert result.status == EmailVerificationStatus.UNDELIVERABLE


@pytest.mark.asyncio
async def test_mx_only_when_smtp_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "email_verification_enabled", True)
    monkeypatch.setattr(settings, "email_verification_smtp_enabled", False)
    monkeypatch.setattr(
        "app.services.lead_discovery.email_verifier._resolve_mx",
        lambda domain: "mx.acme.com",
    )
    result = await verify_email("jane@acme.com")
    assert result.status == EmailVerificationStatus.DELIVERABLE
    assert result.checked_mx is True
    assert result.checked_smtp is False


@pytest.mark.asyncio
async def test_no_mx_is_undeliverable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "email_verification_enabled", True)
    monkeypatch.setattr(
        "app.services.lead_discovery.email_verifier._resolve_mx",
        lambda domain: None,
    )
    result = await verify_email("jane@nodomain.invalid")
    assert result.status == EmailVerificationStatus.UNDELIVERABLE
    assert result.checked_mx is True
