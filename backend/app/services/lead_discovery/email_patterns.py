"""Pure email-pattern inference for the email-reveal flow.

Given a person's name and a company domain, produce the ranked candidate
addresses a B2B contact most likely uses (``first.last@``, ``first@``,
``flast@``, …) with a confidence weight per pattern. This module performs **no**
I/O — verification (MX/SMTP) lives in :mod:`email_verifier`, and a candidate is
never treated as real until verified or explicitly marked ``unverified``.

Pattern prevalence weights are drawn from common B2B email-format
distributions; they are heuristics, not guarantees.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.lead_discovery.dedupe import extract_host

# Strip anything that can't appear in an email local-part token.
_LOCAL_SANITIZE_RE = re.compile(r"[^a-z0-9]+")

# (pattern_id, confidence 0..100). Ordered by typical B2B prevalence.
# Each builder receives sanitized lowercase (first, last) tokens.
_PATTERNS: tuple[tuple[str, int], ...] = (
    ("first.last", 32),
    ("first", 18),
    ("flast", 16),
    ("firstlast", 10),
    ("first_last", 6),
    ("firstl", 5),
    ("f.last", 4),
    ("last", 3),
    ("last.first", 2),
    ("lastf", 2),
)


@dataclass(slots=True, frozen=True)
class EmailCandidate:
    """One ranked candidate email for a person at a domain."""

    email: str
    pattern: str
    confidence: int


def _sanitize_token(value: str | None) -> str:
    if not value:
        return ""
    return _LOCAL_SANITIZE_RE.sub("", value.strip().lower())


def _local_part(pattern: str, first: str, last: str) -> str | None:  # noqa: PLR0911
    """Build the local part for ``pattern`` from sanitized name tokens."""
    f = first
    last_ = last
    fi = first[:1]
    li = last[:1]
    match pattern:
        case "first.last":
            return f"{f}.{last_}" if f and last_ else None
        case "first":
            return f or None
        case "flast":
            return f"{fi}{last_}" if fi and last_ else None
        case "firstlast":
            return f"{f}{last_}" if f and last_ else None
        case "first_last":
            return f"{f}_{last_}" if f and last_ else None
        case "firstl":
            return f"{f}{li}" if f and li else None
        case "f.last":
            return f"{fi}.{last_}" if fi and last_ else None
        case "last":
            return last_ or None
        case "last.first":
            return f"{last_}.{f}" if last_ and f else None
        case "lastf":
            return f"{last_}{fi}" if last_ and fi else None
    return None


def split_full_name(full_name: str | None) -> tuple[str, str]:
    """Split a full name into (first, last); last is the final token."""
    if not full_name:
        return "", ""
    parts = [p for p in full_name.strip().split() if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[-1]


def candidate_emails(
    first: str | None,
    last: str | None,
    domain: str | None,
    *,
    full_name: str | None = None,
) -> list[EmailCandidate]:
    """Return ranked candidate emails for a person at ``domain``.

    Accepts either ``first``/``last`` or a ``full_name`` fallback. The domain
    may be a bare host or a full URL — it's normalized to a registrable host.
    Returns an empty list when there's no usable name token or domain.

    Candidates are de-duplicated by address, keeping the highest-confidence
    pattern, and returned in descending confidence order.
    """
    if (not first and not last) and full_name:
        first, last = split_full_name(full_name)

    f = _sanitize_token(first)
    last_ = _sanitize_token(last)
    host = extract_host(domain) if domain else None
    if not host or (not f and not last_):
        return []

    best: dict[str, EmailCandidate] = {}
    for pattern, confidence in _PATTERNS:
        local = _local_part(pattern, f, last_)
        if not local:
            continue
        email = f"{local}@{host}"
        existing = best.get(email)
        if existing is None or confidence > existing.confidence:
            best[email] = EmailCandidate(email=email, pattern=pattern, confidence=confidence)

    return sorted(best.values(), key=lambda c: c.confidence, reverse=True)
