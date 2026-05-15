"""PII masking helpers for safe logging.

These helpers redact personally identifiable information before it reaches
structured logs. Use ``mask_phone`` for any phone-number field and ``mask_email``
for any email field at log/print sites.
"""

from __future__ import annotations


def mask_phone(s: str | None) -> str:
    """Mask a phone number to expose only the last 4 digits.

    Examples:
        "+15551234567" -> "***4567"
        "555-12"       -> "****"      (fewer than 4 digits -> fully masked)
        ""             -> ""
        None           -> ""

    Args:
        s: Raw phone number in any format (E.164, national, digits-only, etc.).

    Returns:
        A string safe to log. Non-digit characters are stripped before the
        last-4 window is selected.
    """
    if not s:
        return ""
    digits = "".join(c for c in s if c.isdigit())
    if len(digits) < 4:
        return "*" * len(digits) if digits else "****"
    return f"***{digits[-4:]}"


def mask_email(s: str | None) -> str:
    """Mask an email address to expose only the domain.

    Examples:
        "alice@example.com" -> "***@example.com"
        "no-at-sign"        -> "***"
        ""                  -> ""
        None                -> ""

    Args:
        s: Raw email address.

    Returns:
        A string safe to log: the local part is replaced with ``***`` and the
        domain is preserved. If no ``@`` is present, returns ``"***"``.
    """
    if not s:
        return ""
    if "@" not in s:
        return "***"
    _, domain = s.rsplit("@", 1)
    return f"***@{domain}"
