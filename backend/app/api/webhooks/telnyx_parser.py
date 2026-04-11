"""Shared parsing helpers for Telnyx webhook payloads."""

from typing import Any

from fastapi import Request

from app.core.webhook_security import verify_telnyx_webhook


async def verify_and_parse(request: Request, log: Any) -> tuple[str, dict[str, Any]] | None:
    """Verify Telnyx signature and parse the event payload.

    Returns (event_type, event_payload) on success, or None on JSON error.
    """
    await verify_telnyx_webhook(request)

    try:
        payload = await request.json()
    except Exception:
        log.error("invalid_json_payload")
        return None

    data = payload.get("data", {})
    event_type = data.get("event_type", "")
    event_payload = data.get("payload", {})
    return event_type, event_payload


def extract_phone_numbers(payload: dict[Any, Any]) -> tuple[str, str]:
    """Extract and normalize phone numbers from Telnyx payload."""
    from app.utils.phone import normalize_phone_safe

    # Telnyx voice webhooks send "from" and "to" as strings or nested objects
    from_raw = payload.get("from", "")
    if isinstance(from_raw, dict):
        from_number = from_raw.get("phone_number", "")
    else:
        from_number = str(from_raw) if from_raw else ""

    to_raw = payload.get("to", "")
    if isinstance(to_raw, list):
        to_number = to_raw[0].get("phone_number", "") if len(to_raw) > 0 else ""
    elif isinstance(to_raw, dict):
        to_number = to_raw.get("phone_number", "")
    else:
        to_number = str(to_raw) if to_raw else ""

    norm_from = normalize_phone_safe(from_number) or from_number
    norm_to = normalize_phone_safe(to_number) or to_number
    return norm_from, norm_to
