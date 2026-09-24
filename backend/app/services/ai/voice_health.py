"""Bounded, payload-free failure signals shared by realtime voice providers."""

from typing import Any


class VoiceProviderError(RuntimeError):
    """A provider can no longer carry this call; do not silently drop it."""


def event_failure_reason(event: dict[str, Any]) -> str | None:
    """Ignore recoverable protocol errors; recognize exhausted/failed responses."""
    kind = event.get("type")
    if kind == "response.done":
        response = event.get("response") or {}
        if response.get("status") != "failed":
            return None
        error = (response.get("status_details") or {}).get("error") or {}
    elif kind == "error":
        error = event.get("error") or {}
    else:
        return None
    if not isinstance(error, dict):
        return "provider_error"
    code = str(error.get("code") or error.get("type") or "").lower()
    if any(token in code for token in ("rate_limit", "quota", "resource_exhausted", "429")):
        return "rate_limited"
    if kind == "response.done" or any(
        token in code
        for token in (
            "server_error",
            "internal_error",
            "overloaded",
            "unavailable",
            "authentication",
            "invalid_api_key",
        )
    ):
        return "provider_error"
    return None
