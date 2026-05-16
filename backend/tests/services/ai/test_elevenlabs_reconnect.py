"""Tests for ``ElevenLabsTTSSession`` reconnect behaviour.

Pins the contract documented in :meth:`ElevenLabsTTSSession._reconnect`:

* Up to three reconnect attempts with exponential backoff (1s, 2s, 4s).
* Session-scoped ``_reconnect_attempts`` counter increments per attempt
  and resets on a successful reconnect.
* ``elevenlabs_reconnect_total{reason}`` is emitted with the documented
  bounded reasons.
* Circuit breaker is consulted before each reconnect attempt — if the
  breaker is open, the loop bails immediately with ``reason=circuit_open``
  rather than burning attempts on a known-bad provider.
* A mock WebSocket server that disconnects on a schedule exercises the
  full lifecycle: receive loop → disconnect → reconnect → receive loop.

All tests monkeypatch ``_RECONNECT_BACKOFFS`` to short durations so the
suite stays fast (<1s per test) while still exercising the loop.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import importlib
import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pybreaker
import pytest
from prometheus_client import Counter

from app.core.circuit_breakers import (
    ElevenLabsUnavailableError,
    ProviderCircuitBreaker,
    elevenlabs_breaker,
)
from app.core.metrics import elevenlabs_reconnect_total
from app.services.ai import elevenlabs_tts as tts_module
from app.services.ai.elevenlabs_tts import ElevenLabsTTSSession

if TYPE_CHECKING:
    from websockets.asyncio.server import ServerConnection


# ``tests/websockets/`` (a sibling test directory at the same import depth)
# can shadow the third-party ``websockets`` package during pytest collection
# depending on sys.path ordering. Import lazily via ``importlib`` so the
# top-level module import doesn't blow up before the runtime has resolved
# the right ``websockets`` package.
def _ws_server_module() -> Any:
    return importlib.import_module("websockets.asyncio.server")


def _ws_client_module() -> Any:
    return importlib.import_module("websockets.asyncio.client")


def _ws_exceptions_module() -> Any:
    return importlib.import_module("websockets.exceptions")


# --------------------------------------------------------------------------- #
# Mock WebSocket server
# --------------------------------------------------------------------------- #


class _ScheduledDisconnectServer:
    """A localhost WebSocket server that disconnects clients on schedule.

    The server accepts one connection at a time. Each connection follows a
    script supplied at construction time:

    * ``messages_before_close``: number of audio messages to send before
      the server closes the socket (code 1011 — internal error — which
      surfaces as ``ConnectionClosedError`` on the client).
    * ``connections_before_giving_up``: stop accepting any further
      connections after this many. Used to verify the client gives up
      after the configured number of reconnect attempts.

    The server tracks how many connections it has accepted so tests can
    assert the client reconnected the expected number of times.
    """

    def __init__(
        self,
        messages_before_close: int = 1,
        connections_before_giving_up: int = 99,
        close_code: int = 1011,
        disconnect_only_first: bool = False,
    ) -> None:
        self.messages_before_close = messages_before_close
        self.connections_before_giving_up = connections_before_giving_up
        self.close_code = close_code
        # If True, only the first accepted connection disconnects on schedule;
        # subsequent connections stay open until the test tears the server
        # down. Used to verify a single reconnect cycle without triggering
        # cascading reconnects on the new (healthy) connection.
        self.disconnect_only_first = disconnect_only_first
        self.connections_accepted = 0
        self.host: str = "127.0.0.1"
        self.port: int = 0
        self._server: Any | None = None

    async def __aenter__(self) -> _ScheduledDisconnectServer:
        serve = _ws_server_module().serve
        self._server = await serve(self._handler, self.host, 0)
        sock = next(iter(self._server.sockets))
        self.port = sock.getsockname()[1]
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    @property
    def url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    async def _handler(self, ws: ServerConnection) -> None:
        connection_closed_exc = _ws_exceptions_module().ConnectionClosed
        self.connections_accepted += 1
        connection_number = self.connections_accepted

        if connection_number > self.connections_before_giving_up:
            # Refuse: close immediately.
            await ws.close(code=1011, reason="server_giving_up")
            return

        try:
            # Drain the BOS message so the client's send doesn't error.
            with contextlib.suppress(Exception):
                await asyncio.wait_for(ws.recv(), timeout=0.5)

            for i in range(self.messages_before_close):
                payload = {
                    "audio": base64.b64encode(f"chunk-{i}".encode()).decode("ascii"),
                }
                await ws.send(json.dumps(payload))
                await asyncio.sleep(0.01)

            # If configured to disconnect only the first connection, keep
            # subsequent connections alive so the test can observe a stable
            # post-reconnect state without cascading reconnects.
            if self.disconnect_only_first and connection_number > 1:
                # Stay open until the client/test closes us out. ``recv()``
                # blocks until the peer sends or closes.
                with contextlib.suppress(connection_closed_exc, asyncio.TimeoutError):
                    while True:
                        await asyncio.wait_for(ws.recv(), timeout=5.0)
                return

            # Abnormal close → client sees ConnectionClosedError.
            await ws.close(code=self.close_code, reason="scheduled_disconnect")
        except connection_closed_exc:
            return


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def fast_backoffs(monkeypatch: pytest.MonkeyPatch) -> tuple[float, ...]:
    """Shrink reconnect delays so tests stay sub-second.

    Patches the class attribute so every ``ElevenLabsTTSSession`` instance
    in the test sees the short delays, without leaking state between tests.
    """
    fast = (0.01, 0.02, 0.04)
    monkeypatch.setattr(ElevenLabsTTSSession, "_RECONNECT_BACKOFFS", fast)
    return fast


@pytest.fixture(autouse=True)
def reset_breaker() -> None:
    """Force the elevenlabs breaker back to ``closed`` between tests.

    The breaker is a module-level singleton, so failures in one test
    accumulate on its internal counter and can spuriously trip it open
    during a later test. We reset both the failure counter and the
    state machine so each test starts from a clean baseline.
    """
    elevenlabs_breaker.close()
    elevenlabs_breaker._state_storage.reset_counter()


@pytest.fixture
def reset_metric() -> Counter:
    """Reset the reconnect counter to zero before each test."""
    elevenlabs_reconnect_total.clear()
    return elevenlabs_reconnect_total


def _metric_value(reason: str) -> float:
    raw: float = elevenlabs_reconnect_total.labels(reason=reason)._value.get()
    return raw


async def _raise_runtime() -> None:
    raise RuntimeError("boom")


# --------------------------------------------------------------------------- #
# Reconnect loop — unit-level (mock the open_websocket call)
# --------------------------------------------------------------------------- #


class TestReconnectLoop:
    """Cover the reconnect attempt sequence in isolation from the WS server."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(
        self,
        fast_backoffs: tuple[float, ...],
        reset_metric: Counter,
    ) -> None:
        session = ElevenLabsTTSSession(api_key="k", voice_id="v")
        session._output_format = "ulaw_8000"
        session._open_websocket = AsyncMock(return_value=None)  # type: ignore[method-assign]

        ok = await session._reconnect(reason="connection_closed_error")

        assert ok is True
        assert session._reconnect_attempts == 0  # reset on success
        assert session._open_websocket.await_count == 1
        assert _metric_value("connection_closed_error") == 1
        assert _metric_value("success") == 1
        assert _metric_value("exhausted") == 0

    @pytest.mark.asyncio
    async def test_retries_then_succeeds_on_third_attempt(
        self,
        fast_backoffs: tuple[float, ...],
        reset_metric: Counter,
    ) -> None:
        session = ElevenLabsTTSSession(api_key="k", voice_id="v")
        session._output_format = "ulaw_8000"
        side_effects: list[Any] = [
            RuntimeError("attempt 1 down"),
            RuntimeError("attempt 2 down"),
            None,
        ]
        session._open_websocket = AsyncMock(side_effect=side_effects)  # type: ignore[method-assign]

        ok = await session._reconnect(reason="connection_closed")

        assert ok is True
        assert session._open_websocket.await_count == 3
        # Counter resets to 0 on the successful third attempt.
        assert session._reconnect_attempts == 0
        assert _metric_value("connection_closed") == 1
        assert _metric_value("success") == 1

    @pytest.mark.asyncio
    async def test_exhausts_after_three_attempts(
        self,
        fast_backoffs: tuple[float, ...],
        reset_metric: Counter,
    ) -> None:
        session = ElevenLabsTTSSession(api_key="k", voice_id="v")
        session._output_format = "ulaw_8000"
        session._open_websocket = AsyncMock(side_effect=RuntimeError("nope"))  # type: ignore[method-assign]

        ok = await session._reconnect(reason="connection_closed_error")

        assert ok is False
        # Three attempts total — matches len(_RECONNECT_BACKOFFS).
        assert session._open_websocket.await_count == 3
        assert session._reconnect_attempts == 3
        assert _metric_value("exhausted") == 1
        assert _metric_value("success") == 0

    @pytest.mark.asyncio
    async def test_uses_documented_backoff_sequence(
        self,
        monkeypatch: pytest.MonkeyPatch,
        reset_metric: Counter,
    ) -> None:
        """Delays must be 1s, 2s, 4s in order."""
        captured: list[float] = []

        async def fake_sleep(delay: float) -> None:
            captured.append(delay)

        monkeypatch.setattr(tts_module.asyncio, "sleep", fake_sleep)

        session = ElevenLabsTTSSession(api_key="k", voice_id="v")
        session._output_format = "ulaw_8000"
        session._open_websocket = AsyncMock(side_effect=RuntimeError("nope"))  # type: ignore[method-assign]

        await session._reconnect(reason="connection_closed_error")

        # Default class-level backoffs are the documented 1s/2s/4s.
        assert captured == [1.0, 2.0, 4.0]


# --------------------------------------------------------------------------- #
# Circuit-breaker gate
# --------------------------------------------------------------------------- #


class TestCircuitBreakerGate:
    """Reconnect must bail when the breaker is open."""

    @pytest.mark.asyncio
    async def test_skips_when_breaker_open(
        self,
        fast_backoffs: tuple[float, ...],
        reset_metric: Counter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Force the breaker into OPEN state for this test — use an isolated
        # breaker, not the module singleton, to avoid leaking state.
        fake_breaker = ProviderCircuitBreaker(
            provider="elevenlabs_test",
            unavailable_exc=ElevenLabsUnavailableError,
            fail_max=1,
            reset_timeout=60,
        )
        # Trip it.
        with contextlib.suppress(Exception):
            await fake_breaker.call_async(_raise_runtime)
        assert fake_breaker.current_state == pybreaker.STATE_OPEN

        monkeypatch.setattr(tts_module, "elevenlabs_breaker", fake_breaker)

        session = ElevenLabsTTSSession(api_key="k", voice_id="v")
        session._output_format = "ulaw_8000"
        session._open_websocket = AsyncMock(return_value=None)  # type: ignore[method-assign]

        ok = await session._reconnect(reason="connection_closed_error")

        assert ok is False
        # Open-state check fires *before* the attempt is made, so the
        # underlying open_websocket is never called.
        assert session._open_websocket.await_count == 0
        assert _metric_value("circuit_open") == 1
        # The session-scoped attempt counter still ticks for the
        # rejected attempt so logs/dashboards reflect the try.
        assert session._reconnect_attempts == 1

    @pytest.mark.asyncio
    async def test_circuit_open_raised_by_breaker_mid_attempt(
        self,
        fast_backoffs: tuple[float, ...],
        reset_metric: Counter,
    ) -> None:
        """If breaker raises ``ElevenLabsUnavailableError`` we bail with circuit_open."""
        session = ElevenLabsTTSSession(api_key="k", voice_id="v")
        session._output_format = "ulaw_8000"

        async def fake_call_async(func: Any, *args: Any, **kwargs: Any) -> None:
            raise ElevenLabsUnavailableError(detail="breaker opened mid-flight")

        # Patch the breaker's call_async on the module the code uses.
        original = elevenlabs_breaker.call_async
        elevenlabs_breaker.call_async = fake_call_async  # type: ignore[assignment,method-assign]
        try:
            ok = await session._reconnect(reason="connection_closed_error")
        finally:
            elevenlabs_breaker.call_async = original  # type: ignore[method-assign]

        assert ok is False
        assert _metric_value("circuit_open") == 1


# --------------------------------------------------------------------------- #
# End-to-end with a real (mock) WebSocket server
# --------------------------------------------------------------------------- #


class TestEndToEndWithMockServer:
    """Drive the full receive-loop → disconnect → reconnect cycle."""

    @pytest.mark.asyncio
    async def test_reconnects_after_server_disconnect(
        self,
        fast_backoffs: tuple[float, ...],
        reset_metric: Counter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Server kicks the client after one message; client reconnects once."""
        async with _ScheduledDisconnectServer(
            messages_before_close=1,
            connections_before_giving_up=2,  # accept initial + 1 reconnect
            disconnect_only_first=True,
        ) as srv:
            session = await _build_session_for_server(srv)

            # Pull two chunks then stop. The second chunk is delivered by
            # the reconnected session, so seeing it proves the reconnect
            # path executed end-to-end.
            received = await _drain_audio(session, expected_chunks=2, timeout=2.0, stop_after=2)

            assert received[:2] == [b"chunk-0", b"chunk-0"]
            assert srv.connections_accepted == 2
            assert _metric_value("connection_closed_error") >= 1
            assert _metric_value("success") >= 1

            await session.disconnect()

    @pytest.mark.asyncio
    async def test_gives_up_after_three_failed_reconnects(
        self,
        fast_backoffs: tuple[float, ...],
        reset_metric: Counter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Server disconnects then refuses further connections; client exhausts."""
        async with _ScheduledDisconnectServer(
            messages_before_close=1,
            # Accept only the first connection; refuse every reconnect.
            connections_before_giving_up=1,
        ) as srv:
            session = await _build_session_for_server(srv)

            # Stream terminates after the client exhausts reconnect attempts.
            received = await _drain_audio(session, expected_chunks=1, timeout=5.0)

            assert received == [b"chunk-0"]
            assert _metric_value("exhausted") == 1
            # Initial connection + 3 failed reconnect attempts.
            assert srv.connections_accepted == 4

            await session.disconnect()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


async def _build_session_for_server(
    srv: _ScheduledDisconnectServer,
) -> ElevenLabsTTSSession:
    """Build a session whose ``_open_websocket`` points at the mock server."""
    session = ElevenLabsTTSSession(api_key="k", voice_id="v")
    session._output_format = "ulaw_8000"

    async def _open(output_format: str) -> None:
        connect = _ws_client_module().connect
        session.ws = await connect(srv.url)
        # Match production: send the BOS so the handler can drain it.
        await session.ws.send(json.dumps({"text": " "}))

    session._open_websocket = _open  # type: ignore[method-assign]

    # Mimic ``connect()``'s post-open bookkeeping.
    await session._open_websocket("ulaw_8000")
    session._connected = True
    session._receive_task = asyncio.create_task(session._receive_audio_loop())
    return session


async def _drain_audio(
    session: ElevenLabsTTSSession,
    expected_chunks: int,
    timeout: float,
    stop_after: int | None = None,
) -> list[bytes]:
    """Pull chunks until the stream ends, ``timeout`` elapses, or
    ``stop_after`` chunks have been seen.

    ``stop_after`` lets a test observe a partial stream without forcing
    the server to terminate it — useful for asserting on the *first* N
    chunks across a reconnect.
    """
    received: list[bytes] = []

    async def _consume() -> None:
        stream: AsyncIterator[bytes] = session.receive_audio_stream()
        async for chunk in stream:
            received.append(chunk)
            if stop_after is not None and len(received) >= stop_after:
                return

    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(_consume(), timeout=timeout)

    return received
