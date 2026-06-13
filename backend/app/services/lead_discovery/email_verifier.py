"""Config-gated email verification for the reveal flow.

Verification runs in tiers, each opt-in to avoid slow / IP-risky probes in dev:

* **disabled** (default): ``email_verification_enabled`` is ``False`` → returns
  ``UNKNOWN`` immediately. Pattern-inferred emails stay ``unverified``.
* **MX**: when verification is enabled, confirm the domain has at least one MX
  (or A) record. A domain that can't receive mail invalidates every candidate.
* **SMTP RCPT** (``email_verification_smtp_enabled``): connect to the MX and
  issue ``RCPT TO`` to probe whether the mailbox exists. Slow, and many
  providers grey-list or always-accept (catch-all), so the result is advisory.

This module **never raises into callers** — every failure degrades to a status
with a confidence, so the enrichment worker / reveal endpoint can always record
an audit row.
"""

from __future__ import annotations

import asyncio
import smtplib
from dataclasses import dataclass
from enum import StrEnum

import structlog

from app.core.config import settings
from app.services.lead_discovery.dedupe import extract_host

logger = structlog.get_logger()


class EmailVerificationStatus(StrEnum):
    """Outcome of an email-verification attempt."""

    VERIFIED = "verified"  # mailbox accepted at SMTP RCPT
    DELIVERABLE = "deliverable"  # domain accepts mail (MX ok), mailbox unprobed
    RISKY = "risky"  # catch-all / inconclusive SMTP
    UNDELIVERABLE = "undeliverable"  # no MX, or mailbox rejected
    UNKNOWN = "unknown"  # verification disabled or probe failed


@dataclass(slots=True, frozen=True)
class EmailVerificationResult:
    """Verification verdict for one email address."""

    status: EmailVerificationStatus
    confidence: int  # 0..100
    checked_mx: bool = False
    checked_smtp: bool = False
    mx_host: str | None = None
    detail: str | None = None


_UNKNOWN = EmailVerificationResult(
    status=EmailVerificationStatus.UNKNOWN, confidence=0, detail="verification_disabled"
)


def _resolve_mx(domain: str) -> str | None:
    """Return the lowest-preference MX host for ``domain`` (sync, threaded).

    Falls back to the domain itself when it has an A record but no MX (implicit
    MX). Returns ``None`` when the domain can't receive mail.
    """
    try:
        import dns.resolver  # imported lazily; transitive via email-validator
    except ImportError:  # pragma: no cover - dnspython ships with deps
        return None
    try:
        answers = dns.resolver.resolve(domain, "MX")
        records = sorted(answers, key=lambda r: r.preference)
        if records:
            return str(records[0].exchange).rstrip(".")
    except Exception:  # noqa: BLE001 - any DNS failure -> try implicit MX
        pass
    try:
        dns.resolver.resolve(domain, "A")
        return domain
    except Exception:  # noqa: BLE001 - no mail-capable record
        return None


def _smtp_probe(mx_host: str, email: str) -> tuple[bool | None, str]:
    """Probe ``email`` via SMTP RCPT against ``mx_host`` (sync, threaded).

    Returns ``(accepted, detail)`` where ``accepted`` is ``True`` (mailbox
    accepted), ``False`` (rejected), or ``None`` (inconclusive / catch-all risk).
    """
    timeout = settings.email_verification_smtp_timeout_seconds
    sender = settings.email_verification_smtp_from
    try:
        with smtplib.SMTP(mx_host, 25, timeout=timeout) as smtp:
            smtp.ehlo_or_helo_if_needed()
            smtp.mail(sender)
            code, _ = smtp.rcpt(email)
            if 200 <= code < 300:
                return True, f"rcpt_{code}"
            if code in (550, 551, 553):
                return False, f"rcpt_{code}"
            return None, f"rcpt_{code}"
    except Exception as exc:  # noqa: BLE001 - network/greylist -> inconclusive
        return None, f"smtp_error:{type(exc).__name__}"


async def verify_email(email: str) -> EmailVerificationResult:
    """Verify ``email`` per the configured tier. Never raises.

    Returns an :class:`EmailVerificationResult`; ``UNKNOWN`` when verification
    is disabled or DNS/SMTP probing can't reach a verdict.
    """
    if not settings.email_verification_enabled:
        return _UNKNOWN
    if "@" not in email:
        return EmailVerificationResult(
            status=EmailVerificationStatus.UNDELIVERABLE,
            confidence=0,
            detail="malformed",
        )

    domain = email.rsplit("@", 1)[1]
    host = extract_host(domain) or domain
    log = logger.bind(component="email_verifier", domain=host)

    mx_host = await asyncio.to_thread(_resolve_mx, host)
    if mx_host is None:
        return EmailVerificationResult(
            status=EmailVerificationStatus.UNDELIVERABLE,
            confidence=5,
            checked_mx=True,
            detail="no_mx",
        )

    if not settings.email_verification_smtp_enabled:
        # MX exists, mailbox unprobed — domain can receive mail.
        return EmailVerificationResult(
            status=EmailVerificationStatus.DELIVERABLE,
            confidence=55,
            checked_mx=True,
            mx_host=mx_host,
            detail="mx_only",
        )

    accepted, detail = await asyncio.to_thread(_smtp_probe, mx_host, email)
    if accepted is True:
        result = EmailVerificationResult(
            status=EmailVerificationStatus.VERIFIED,
            confidence=92,
            checked_mx=True,
            checked_smtp=True,
            mx_host=mx_host,
            detail=detail,
        )
    elif accepted is False:
        result = EmailVerificationResult(
            status=EmailVerificationStatus.UNDELIVERABLE,
            confidence=8,
            checked_mx=True,
            checked_smtp=True,
            mx_host=mx_host,
            detail=detail,
        )
    else:
        result = EmailVerificationResult(
            status=EmailVerificationStatus.RISKY,
            confidence=45,
            checked_mx=True,
            checked_smtp=True,
            mx_host=mx_host,
            detail=detail,
        )
    log.info("email_verified", status=result.status.value, detail=detail)
    return result
