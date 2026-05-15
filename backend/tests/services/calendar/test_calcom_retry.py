"""Tests for `CalComService._request_with_retry`.

Covers the narrowed retry policy:
- 4xx responses are terminal (no retry).
- 5xx responses retry with exponential backoff + jitter.
- Network/timeout errors retry, then surface CalComError on exhaustion.
- Retry-After header is honored, accepting both delta-seconds and HTTP-date.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.calendar.calcom import (
    CalComError,
    CalComNotFoundError,
    CalComRateLimitError,
    CalComService,
    _parse_retry_after,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(
    status_code: int,
    *,
    json_body: dict[str, Any] | None = None,
    text: str = "",
    headers: dict[str, str] | None = None,
) -> MagicMock:
    """Build a MagicMock that quacks like httpx.Response for our code path."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    resp.headers = headers or {}
    resp.json = MagicMock(return_value=json_body or {})
    return resp


@pytest.fixture
def service() -> CalComService:
    return CalComService(api_key="test-key")


@pytest.fixture
def mock_client() -> AsyncMock:
    client = AsyncMock(spec=httpx.AsyncClient)
    return client


@pytest.fixture(autouse=True)
def _no_sleep() -> Any:
    """Make asyncio.sleep instant so retry loops run quickly."""
    with patch(
        "app.services.calendar.calcom.asyncio.sleep", new=AsyncMock(return_value=None)
    ) as mock_sleep:
        yield mock_sleep


@pytest.fixture(autouse=True)
def _deterministic_jitter() -> Any:
    """Pin random.uniform so jitter is deterministic in assertions."""
    with patch("app.services.calendar.calcom.random.uniform", return_value=0.0) as mock_uniform:
        yield mock_uniform


# ---------------------------------------------------------------------------
# 4xx — no retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_4xx_client_error_is_not_retried(
    service: CalComService, mock_client: AsyncMock, _no_sleep: AsyncMock
) -> None:
    mock_client.request.return_value = _make_response(400, text="bad request")

    with pytest.raises(CalComError) as excinfo:
        await service._request_with_retry("GET", "https://api.cal.com/v2/x", mock_client)

    assert "bad request" in str(excinfo.value)
    assert mock_client.request.await_count == 1
    assert _no_sleep.await_count == 0


@pytest.mark.asyncio
async def test_404_raises_not_found_without_retry(
    service: CalComService, mock_client: AsyncMock
) -> None:
    mock_client.request.return_value = _make_response(404)

    with pytest.raises(CalComNotFoundError):
        await service._request_with_retry("GET", "https://api.cal.com/v2/x", mock_client)

    assert mock_client.request.await_count == 1


# ---------------------------------------------------------------------------
# 5xx — retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_5xx_retries_then_succeeds(
    service: CalComService, mock_client: AsyncMock, _no_sleep: AsyncMock
) -> None:
    mock_client.request.side_effect = [
        _make_response(500, text="boom"),
        _make_response(502, text="bad gateway"),
        _make_response(200, json_body={"ok": True}),
    ]

    result = await service._request_with_retry("GET", "https://api.cal.com/v2/x", mock_client)

    assert result == {"ok": True}
    assert mock_client.request.await_count == 3
    # Two sleeps between the three attempts.
    assert _no_sleep.await_count == 2


@pytest.mark.asyncio
async def test_5xx_exhausts_retries_and_raises(
    service: CalComService, mock_client: AsyncMock
) -> None:
    mock_client.request.return_value = _make_response(503, text="unavailable")

    with pytest.raises(CalComError):
        await service._request_with_retry("GET", "https://api.cal.com/v2/x", mock_client)

    assert mock_client.request.await_count == 3


# ---------------------------------------------------------------------------
# Network / timeout — retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_network_error_retries_then_succeeds(
    service: CalComService, mock_client: AsyncMock
) -> None:
    mock_client.request.side_effect = [
        httpx.ConnectError("connection refused"),
        _make_response(200, json_body={"ok": True}),
    ]

    result = await service._request_with_retry("GET", "https://api.cal.com/v2/x", mock_client)

    assert result == {"ok": True}
    assert mock_client.request.await_count == 2


@pytest.mark.asyncio
async def test_timeout_retries_then_exhausts(
    service: CalComService, mock_client: AsyncMock
) -> None:
    mock_client.request.side_effect = httpx.ReadTimeout("timed out")

    with pytest.raises(CalComError, match="timeout"):
        await service._request_with_retry("GET", "https://api.cal.com/v2/x", mock_client)

    assert mock_client.request.await_count == 3


@pytest.mark.asyncio
async def test_unrelated_exception_is_not_retried(
    service: CalComService, mock_client: AsyncMock
) -> None:
    """RuntimeError (or any non-httpx exception) must bubble immediately."""
    mock_client.request.side_effect = RuntimeError("unexpected")

    with pytest.raises(RuntimeError, match="unexpected"):
        await service._request_with_retry("GET", "https://api.cal.com/v2/x", mock_client)

    assert mock_client.request.await_count == 1


# ---------------------------------------------------------------------------
# Retry-After header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_after_integer_seconds_is_honored(
    service: CalComService, mock_client: AsyncMock, _no_sleep: AsyncMock
) -> None:
    mock_client.request.side_effect = [
        _make_response(429, headers={"retry-after": "7"}),
        _make_response(200, json_body={"ok": True}),
    ]

    result = await service._request_with_retry("GET", "https://api.cal.com/v2/x", mock_client)

    assert result == {"ok": True}
    # First (and only) sleep should be the parsed retry-after.
    _no_sleep.assert_awaited_once_with(7.0)


@pytest.mark.asyncio
async def test_retry_after_http_date_is_honored(
    service: CalComService, mock_client: AsyncMock, _no_sleep: AsyncMock
) -> None:
    future = datetime.now(UTC) + timedelta(seconds=12)
    http_date = format_datetime(future, usegmt=True)

    mock_client.request.side_effect = [
        _make_response(429, headers={"retry-after": http_date}),
        _make_response(200, json_body={"ok": True}),
    ]

    result = await service._request_with_retry("GET", "https://api.cal.com/v2/x", mock_client)

    assert result == {"ok": True}
    _no_sleep.assert_awaited_once()
    assert _no_sleep.await_args is not None
    slept_for = _no_sleep.await_args.args[0]
    # Allow a generous window for clock drift between header generation and parsing.
    assert 0 <= slept_for <= 13


@pytest.mark.asyncio
async def test_retry_after_past_http_date_clamps_to_zero(
    service: CalComService, mock_client: AsyncMock, _no_sleep: AsyncMock
) -> None:
    past = datetime.now(UTC) - timedelta(seconds=30)
    http_date = format_datetime(past, usegmt=True)

    mock_client.request.side_effect = [
        _make_response(429, headers={"retry-after": http_date}),
        _make_response(200, json_body={"ok": True}),
    ]

    await service._request_with_retry("GET", "https://api.cal.com/v2/x", mock_client)

    _no_sleep.assert_awaited_once_with(0.0)


@pytest.mark.asyncio
async def test_429_exhausts_retries_raises_rate_limit_error(
    service: CalComService, mock_client: AsyncMock
) -> None:
    mock_client.request.return_value = _make_response(429, headers={"retry-after": "1"})

    with pytest.raises(CalComRateLimitError):
        await service._request_with_retry("GET", "https://api.cal.com/v2/x", mock_client)

    assert mock_client.request.await_count == 3


# ---------------------------------------------------------------------------
# Jitter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backoff_includes_random_jitter(
    service: CalComService, mock_client: AsyncMock, _no_sleep: AsyncMock
) -> None:
    """random.uniform(0, backoff_seconds) is added to the current backoff each retry."""
    with patch("app.services.calendar.calcom.random.uniform", return_value=0.5) as mock_uniform:
        mock_client.request.side_effect = [
            _make_response(500),
            _make_response(500),
            _make_response(200, json_body={"ok": True}),
        ]

        await service._request_with_retry("GET", "https://api.cal.com/v2/x", mock_client)

    # First retry sleeps at the initial backoff (1.0), second at jittered next.
    sleeps = [call.args[0] for call in _no_sleep.await_args_list]
    assert sleeps == [1.0, 1.5]
    # Called once per successful retry transition (2 transitions here).
    assert mock_uniform.call_count == 2


# ---------------------------------------------------------------------------
# _parse_retry_after — direct unit tests
# ---------------------------------------------------------------------------


def test_parse_retry_after_returns_fallback_when_missing() -> None:
    assert _parse_retry_after(None, fallback=4.0) == 4.0


def test_parse_retry_after_returns_fallback_when_empty() -> None:
    assert _parse_retry_after("   ", fallback=2.5) == 2.5


def test_parse_retry_after_parses_integer() -> None:
    assert _parse_retry_after("15", fallback=1.0) == 15.0


def test_parse_retry_after_parses_http_date() -> None:
    future = datetime.now(UTC) + timedelta(seconds=20)
    result = _parse_retry_after(format_datetime(future, usegmt=True), fallback=1.0)
    assert 18 <= result <= 21


def test_parse_retry_after_malformed_returns_fallback() -> None:
    assert _parse_retry_after("not a date", fallback=3.0) == 3.0
