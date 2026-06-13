"""Dedupe helpers for normalized lead candidates.

The lead miner stores one row per logical lead per workspace. To keep the
``(workspace_id, dedupe_key)`` unique constraint honest, every provider's
output must run through the same normalization → hash pipeline before it can
land in ``lead_prospects``.

The strongest available identifier wins, in this order:

1. phone number (E.164)
2. email address (lowercased)
3. website host (lowercased, ``www.`` stripped)
4. owner name (lowercased, punctuation collapsed)

If none of the four are populated, the lead has no dedupe key. The caller is
free to skip it, persist with ``dedupe_key=NULL`` (Postgres treats NULL as
distinct in the unique constraint), or attach an artificial key from
``source_external_id`` themselves.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlparse

from app.core.encryption import hash_value
from app.services.lead_discovery.types import RawLead
from app.utils.phone import normalize_phone_safe

_WHITESPACE_RE = re.compile(r"\s+")
_OWNER_PUNCT_RE = re.compile(r"[^\w\s]+")

# Facet prefixes prevent collisions between identifier types — without them,
# a phone literally equal to an email's local-part could share a dedupe key.
_PHONE_FACET = "phone"
_EMAIL_FACET = "email"
_WEBSITE_FACET = "website"
_OWNER_FACET = "owner"
# Person facet binds an individual's name to the company host so two different
# people at the same domain don't collide on the host-only website key.
_PERSON_FACET = "person"


# ---------------------------------------------------------------------------
# Normalizers (pure, no I/O)
# ---------------------------------------------------------------------------


def normalize_phone_for_dedupe(phone: str | None) -> str | None:
    """Return the E.164 form of ``phone`` or ``None`` if it can't be parsed.

    Wraps ``app.utils.phone.normalize_phone_safe`` so phone-format quirks
    (parens, dashes, country prefixes) collapse to a single dedupe key.
    """
    if phone is None:
        return None
    candidate = phone.strip()
    if not candidate:
        return None
    return normalize_phone_safe(candidate)


def normalize_email_for_dedupe(email: str | None) -> str | None:
    """Return ``email`` lowercased + trimmed, or ``None`` if missing/empty.

    Does not validate the address — providers that emit garbage emails will
    still produce a deterministic key, and downstream enrichment is free to
    reject them later.
    """
    if email is None:
        return None
    candidate = email.strip().lower()
    if not candidate:
        return None
    return candidate


def extract_host(website: str | None) -> str | None:
    """Return the lowercase host of ``website`` with ``www.`` stripped.

    Accepts both schemeful (``https://example.com/foo``) and bare
    (``example.com/foo``) inputs. Returns ``None`` if no host can be
    extracted.
    """
    if website is None:
        return None
    candidate = website.strip()
    if not candidate:
        return None
    if "://" not in candidate:
        candidate = f"http://{candidate}"
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    return host or None


def normalize_website_host_for_dedupe(website: str | None) -> str | None:
    """Public alias for :func:`extract_host` used by dedupe callers."""
    return extract_host(website)


def normalize_owner_name_for_dedupe(name: str | None) -> str | None:
    """Collapse whitespace and punctuation in ``name``, lowercase the result.

    "  John  P. O'Brien-Jr.  " → ``"john p obrienjr"``. Owner-name keys are a
    weak last-resort identifier; the canonical normalization here is good
    enough to dedupe runs of the same provider against itself but should not
    be relied on for cross-source identity.
    """
    if name is None:
        return None
    stripped = name.strip()
    if not stripped:
        return None
    no_punct = _OWNER_PUNCT_RE.sub("", stripped)
    collapsed = _WHITESPACE_RE.sub(" ", no_punct).strip().lower()
    return collapsed or None


# ---------------------------------------------------------------------------
# Per-facet key builders
# ---------------------------------------------------------------------------


def _hash_with_facet(facet: str, value: str) -> str:
    """Hash ``facet:value`` so different facets never collide on a literal."""
    return hash_value(f"{facet}:{value}")


def dedupe_key_for_phone(phone: str | None) -> str | None:
    """Return the workspace-deterministic dedupe key for ``phone``."""
    normalized = normalize_phone_for_dedupe(phone)
    if normalized is None:
        return None
    return _hash_with_facet(_PHONE_FACET, normalized)


def dedupe_key_for_email(email: str | None) -> str | None:
    """Return the workspace-deterministic dedupe key for ``email``."""
    normalized = normalize_email_for_dedupe(email)
    if normalized is None:
        return None
    return _hash_with_facet(_EMAIL_FACET, normalized)


def dedupe_key_for_website(website: str | None) -> str | None:
    """Return the workspace-deterministic dedupe key for ``website``."""
    host = extract_host(website)
    if host is None:
        return None
    return _hash_with_facet(_WEBSITE_FACET, host)


def dedupe_key_for_owner_name(name: str | None) -> str | None:
    """Return the workspace-deterministic dedupe key for an owner name."""
    normalized = normalize_owner_name_for_dedupe(name)
    if normalized is None:
        return None
    return _hash_with_facet(_OWNER_FACET, normalized)


def dedupe_key_for_person(
    *,
    email: str | None = None,
    full_name: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    website: str | None = None,
    website_host: str | None = None,
) -> str | None:
    """Return a person-level dedupe key (email, else name+host).

    People extraction emits *named individuals* at a company, so two distinct
    people at the same domain must not collapse onto the company's host-only
    website key. Priority:

    1. email (strongest — globally unique) → reuses the email facet so a person
       row and a contact row with the same address still merge.
    2. ``person:<normalized name>@<host>`` — binds the individual to the
       company so same-name people at different companies stay distinct and
       same-company different people stay distinct.

    Returns ``None`` when neither a usable email nor a name+host pair exists.
    """
    email_key = dedupe_key_for_email(email)
    if email_key is not None:
        return email_key

    name = full_name or _combine_first_last(first_name, last_name)
    normalized_name = normalize_owner_name_for_dedupe(name)
    host = extract_host(website_host or website)
    if normalized_name is None or host is None:
        return None
    return _hash_with_facet(_PERSON_FACET, f"{normalized_name}@{host}")


# ---------------------------------------------------------------------------
# Lead-level key + batch dedupe
# ---------------------------------------------------------------------------


def dedupe_key_for_lead(lead: RawLead) -> str | None:
    """Pick the strongest identifier on ``lead`` and return its dedupe key.

    Priority is phone > email > website > owner name. Returns ``None`` when
    the lead carries none of the four — callers decide whether to drop the
    lead, attach a synthetic key, or persist with a NULL dedupe column.
    """
    phone_key = dedupe_key_for_phone(lead.phone_number)
    if phone_key is not None:
        return phone_key

    email_key = dedupe_key_for_email(lead.email)
    if email_key is not None:
        return email_key

    # Prefer the precomputed host if the provider supplied one — it lets us
    # dedupe even when the raw URL is missing.
    website_source = lead.website_host or lead.website
    website_key = dedupe_key_for_website(website_source)
    if website_key is not None:
        return website_key

    name_candidate = lead.full_name or _combine_first_last(lead.first_name, lead.last_name)
    return dedupe_key_for_owner_name(name_candidate)


def _combine_first_last(first: str | None, last: str | None) -> str | None:
    """Return ``"first last"`` (whichever side is present)."""
    parts = [p for p in (first, last) if p and p.strip()]
    if not parts:
        return None
    return " ".join(parts)


def dedupe_raw_leads(
    leads: Iterable[RawLead],
) -> tuple[tuple[RawLead, ...], int]:
    """Drop within-batch duplicates from ``leads`` preserving input order.

    Two leads collide when they share a non-null dedupe key. Leads without a
    key are always kept — they're the safest default, and the lead miner can
    sort them out at persistence time.

    Returns:
        ``(unique_leads, duplicate_count)`` — ``unique_leads`` preserves
        original ordering; ``duplicate_count`` is the number of inputs that
        collided with an earlier one.
    """
    seen: set[str] = set()
    unique: list[RawLead] = []
    duplicates = 0
    for lead in leads:
        key = dedupe_key_for_lead(lead)
        if key is not None:
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
        unique.append(lead)
    return tuple(unique), duplicates
