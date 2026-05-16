"""ElevenLabs Text-to-Speech WebSocket streaming client.

Provides streaming TTS via ElevenLabs WebSocket API with direct ulaw_8000 output
for Telnyx telephony integration (no audio conversion needed).
"""

import asyncio
import base64
import contextlib
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import pybreaker
import structlog
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from app.core.circuit_breakers import ElevenLabsUnavailableError, elevenlabs_breaker
from app.core.metrics import elevenlabs_reconnect_total, elevenlabs_tts_latency_ms

logger = structlog.get_logger()

# ElevenLabs available voices (subset of popular voices)
ELEVENLABS_VOICES = {
    "ava": {"id": "gJx1vCzNCD1EQHT212Ls", "name": "Ava", "description": "Natural female"},
    "lisa": {"id": "lRS76KmLyt8TypvcyLlV", "name": "Lisa", "description": "Friendly female"},
    "sarah_eve": {
        "id": "nf4MCGNSdM0hxM95ZBQR",
        "name": "Sarah Eve",
        "description": "Expressive female",
    },
    "rachel": {"id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel", "description": "Calm female"},
    "bella": {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Bella", "description": "Soft female"},
    "antoni": {"id": "ErXwobaYiN019PkySvjV", "name": "Antoni", "description": "Young male"},
    "josh": {"id": "TxGEqnHWrfWFTfGW9XjX", "name": "Josh", "description": "Deep male"},
    "adam": {"id": "pNInz6obpgDQGcFmaJgB", "name": "Adam", "description": "Narrator male"},
    "sam": {"id": "yoZ06aMxZJJ28mfd3POQ", "name": "Sam", "description": "Raspy male"},
    "domi": {"id": "AZnzlk1XvdvUeBnXmlld", "name": "Domi", "description": "Strong female"},
    "elli": {"id": "MF3mGyEYCl7XYWbV9V6O", "name": "Elli", "description": "Young female"},
    "callum": {"id": "N2lVS1w4EtoT3dr4eOWO", "name": "Callum", "description": "Transatlantic male"},
    "charlie": {"id": "IKne3meq5aSn9XLyUdCD", "name": "Charlie", "description": "Casual male"},
    "charlotte": {
        "id": "XB0fDUnXU5powFXDhCwa",
        "name": "Charlotte",
        "description": "Swedish female",
    },
    "clyde": {"id": "2EiwWnXFnvU5JabPnv8n", "name": "Clyde", "description": "War veteran male"},
    "daniel": {"id": "onwK4e9ZLuTAKqWW03F9", "name": "Daniel", "description": "British male"},
    "dave": {"id": "CYw3kZ02Hs0563khs1Fj", "name": "Dave", "description": "British essayist"},
    "emily": {"id": "LcfcDJNUP1GQjkzn1xUU", "name": "Emily", "description": "Calm female"},
    "ethan": {"id": "g5CIjZEefAph4nQFvHAz", "name": "Ethan", "description": "Neutral male"},
    "freya": {"id": "jsCqWAovK2LkecY7zXl4", "name": "Freya", "description": "American female"},
    "gigi": {"id": "jBpfuIE2acCO8z3wKNLl", "name": "Gigi", "description": "Childlike female"},
    "giovanni": {"id": "zcAOhNBS3c14rBihAFp1", "name": "Giovanni", "description": "Italian male"},
    "glinda": {"id": "z9fAnlkpzviPz146aGWa", "name": "Glinda", "description": "Witch female"},
    "grace": {"id": "oWAxZDx7w5VEj9dCyTzz", "name": "Grace", "description": "Southern female"},
    "harry": {"id": "SOYHLrjzK2X1ezoPC6cr", "name": "Harry", "description": "Anxious male"},
    "james": {"id": "ZQe5CZNOzWyzPSCn5a3c", "name": "James", "description": "Australian male"},
    "jeremy": {"id": "bVMeCyTHy58xNoL34h3p", "name": "Jeremy", "description": "Irish male"},
    "jessie": {"id": "t0jbNlBVZ17f02VDIeMI", "name": "Jessie", "description": "Raspy male"},
    "joseph": {"id": "Zlb1dXrM653N07WRdFW3", "name": "Joseph", "description": "British male"},
    "lily": {"id": "pFZP5JQG7iQjIQuC4Bku", "name": "Lily", "description": "British female"},
    "matilda": {"id": "XrExE9yKIg1WjnnlVkGX", "name": "Matilda", "description": "Warm female"},
    "michael": {"id": "flq6f7yk4E4fJM5XTYuZ", "name": "Michael", "description": "Old male"},
    "mimi": {"id": "zrHiDhphv9ZnVXBqCLjz", "name": "Mimi", "description": "Swedish female"},
    "nicole": {"id": "piTKgcLEGmPE4e6mEKli", "name": "Nicole", "description": "Soft female"},
    "patrick": {"id": "ODq5zmih8GrVes37Dizd", "name": "Patrick", "description": "Shouty male"},
    "river": {"id": "SAz9YHcvj6GT2YYXdXww", "name": "River", "description": "Confident female"},
    "sarah": {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Sarah", "description": "Soft female"},
    "serena": {"id": "pMsXgVXv3BLzUgSXRplE", "name": "Serena", "description": "Pleasant female"},
    "thomas": {"id": "GBv7mTt0atIp3Br8iCZE", "name": "Thomas", "description": "Calm male"},
    "victoria": {"id": "7p1Ofvcwsv7UBPoFN8wY", "name": "Victoria", "description": "Elegant female"},
}


class ElevenLabsTTSSession:
    """ElevenLabs streaming TTS via WebSocket.

    Provides text-to-speech conversion using ElevenLabs' streaming WebSocket API.
    Outputs audio in ulaw_8000 format, which is Telnyx's native format (no conversion needed).
    """

    BASE_URL = "wss://api.elevenlabs.io/v1/text-to-speech"
    MODEL_ID = "eleven_flash_v2_5"  # Fast, low-latency model for telephony
    V3_CONVERSATIONAL_MODEL_ID = "eleven_v3_conversational"  # Most expressive, higher latency

    def __init__(
        self,
        api_key: str,
        voice_id: str = "21m00Tcm4TlvDq8ikWAM",
        model_id: str | None = None,
    ) -> None:
        """Initialize ElevenLabs TTS session.

        Args:
            api_key: ElevenLabs API key
            voice_id: Voice ID (default: Rachel)
            model_id: Model ID (default: eleven_flash_v2_5)
        """
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id or self.MODEL_ID
        self.ws: ClientConnection | None = None
        self.logger = logger.bind(service="elevenlabs_tts")
        self._audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._receive_task: asyncio.Task[None] | None = None
        self._connected = False
        # Monotonic timestamp of the most recent send_text() call. Cleared
        # on first audio chunk so we measure first-byte TTS latency without
        # double-counting subsequent chunks of the same utterance.
        self._pending_send_text_at: float | None = None
        # Output format retained so a reconnect can re-open with the same
        # negotiated audio encoding. Populated by ``connect()``.
        self._output_format: str = "ulaw_8000"
        # Session-scoped reconnect attempt counter. Increments on every
        # reconnect attempt and resets to 0 on a successful reconnect, so the
        # value visible mid-loop is the number of attempts spent on the
        # *current* outage rather than a lifetime total.
        self._reconnect_attempts: int = 0

    # Exponential backoff delays (seconds) between reconnect attempts.
    # 1s -> 2s -> 4s, 3 attempts total before surfacing the error.
    _RECONNECT_BACKOFFS: tuple[float, ...] = (1.0, 2.0, 4.0)

    async def connect(self, output_format: str = "ulaw_8000") -> bool:
        """Connect to ElevenLabs WebSocket API.

        Args:
            output_format: Output audio format (default: ulaw_8000 for Telnyx)

        Returns:
            True if successful, False otherwise
        """
        self.logger.info(
            "connecting_to_elevenlabs",
            voice_id=self.voice_id,
            output_format=output_format,
        )

        self._output_format = output_format
        try:
            await elevenlabs_breaker.call_async(self._open_websocket, output_format)
        except ElevenLabsUnavailableError as e:
            self.logger.warning(
                "elevenlabs_circuit_open",
                voice_id=self.voice_id,
                error=str(e),
            )
            return False
        except Exception as e:
            self.logger.exception("elevenlabs_connection_failed", error=str(e))
            return False

        self._connected = True
        self.logger.info("connected_to_elevenlabs")
        # Start background task to receive audio
        self._receive_task = asyncio.create_task(self._receive_audio_loop())
        return True

    async def _reconnect(self, reason: str) -> bool:
        """Attempt to re-open the ElevenLabs WebSocket with exponential backoff.

        Runs up to ``len(self._RECONNECT_BACKOFFS)`` attempts (3 by default)
        with delays 1s, 2s, 4s. Before each attempt, the ElevenLabs circuit
        breaker is consulted: if it is in the ``open`` state we skip the
        attempt entirely, emit ``elevenlabs_reconnect_total{reason=circuit_open}``,
        and return ``False`` so the caller surfaces the error to its caller
        rather than burning the remaining attempts on a known-bad provider.

        On success, ``self.ws`` is replaced with the new connection, the
        session-scoped attempt counter is reset to 0, and ``True`` is
        returned. On exhaustion the counter is left at its final value so
        observability surfaces show the full attempt history for the
        incident, and ``False`` is returned.

        Args:
            reason: Bounded enum describing why the reconnect was triggered
                (``connection_closed`` / ``connection_closed_error``). Used
                as the metric label for the trigger event and propagated to
                structured logs.

        Returns:
            True if a reconnect attempt succeeded, False otherwise.
        """
        # Record the trigger that prompted the reconnect attempt loop. This
        # increments once per outage (not per attempt) so the counter
        # measures *incidents* by root cause, and per-attempt outcomes
        # (``success`` / ``exhausted`` / ``circuit_open``) are emitted below.
        elevenlabs_reconnect_total.labels(reason=reason).inc()

        for delay in self._RECONNECT_BACKOFFS:
            self._reconnect_attempts += 1
            attempt = self._reconnect_attempts

            # Circuit-breaker gate: if the breaker tripped while we were
            # disconnected, don't waste an attempt — surface the failure so
            # the caller can fall back. We read ``current_state`` directly
            # rather than calling through the breaker so the gate itself
            # doesn't burn a probe slot.
            if elevenlabs_breaker.current_state == pybreaker.STATE_OPEN:
                self.logger.warning(
                    "elevenlabs_reconnect_skipped_circuit_open",
                    attempt=attempt,
                    voice_id=self.voice_id,
                )
                elevenlabs_reconnect_total.labels(reason="circuit_open").inc()
                return False

            self.logger.info(
                "elevenlabs_reconnect_attempt",
                attempt=attempt,
                delay_seconds=delay,
                voice_id=self.voice_id,
            )
            await asyncio.sleep(delay)

            try:
                await elevenlabs_breaker.call_async(self._open_websocket, self._output_format)
            except ElevenLabsUnavailableError as e:
                # Breaker tripped mid-loop; treat the same as the pre-check.
                self.logger.warning(
                    "elevenlabs_reconnect_circuit_open",
                    attempt=attempt,
                    error=str(e),
                )
                elevenlabs_reconnect_total.labels(reason="circuit_open").inc()
                return False
            except Exception as e:
                self.logger.warning(
                    "elevenlabs_reconnect_failed",
                    attempt=attempt,
                    error=str(e),
                )
                continue

            # Success — connection is live again.
            self.logger.info(
                "elevenlabs_reconnect_succeeded",
                attempt=attempt,
                voice_id=self.voice_id,
            )
            elevenlabs_reconnect_total.labels(reason="success").inc()
            self._connected = True
            self._reconnect_attempts = 0
            return True

        self.logger.error(
            "elevenlabs_reconnect_exhausted",
            attempts=self._reconnect_attempts,
            voice_id=self.voice_id,
        )
        elevenlabs_reconnect_total.labels(reason="exhausted").inc()
        return False

    async def _open_websocket(self, output_format: str) -> None:
        """Open the WebSocket and send the BOS message.

        Extracted so the circuit breaker can observe raw exceptions —
        :meth:`connect`'s ``try/except`` would otherwise swallow them
        before the breaker increments its failure counter.
        """
        url = (
            f"{self.BASE_URL}/{self.voice_id}/stream-input"
            f"?model_id={self.model_id}"
            f"&output_format={output_format}"
        )
        self.ws = await connect(
            url,
            additional_headers={"xi-api-key": self.api_key},
        )
        bos_message = {
            "text": " ",  # Required space to start
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
            "xi_api_key": self.api_key,
        }
        await self.ws.send(json.dumps(bos_message))

    async def disconnect(self) -> None:
        """Disconnect from ElevenLabs WebSocket API."""
        self._connected = False

        # Cancel receive task
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task
            self._receive_task = None

        # Close WebSocket
        if self.ws:
            try:
                # Send End of Stream (EOS) message
                eos_message = {"text": ""}
                await self.ws.send(json.dumps(eos_message))
                await self.ws.close()
            except Exception as e:
                self.logger.exception("elevenlabs_disconnect_error", error=str(e))
            self.ws = None

        # Signal end of audio stream
        await self._audio_queue.put(None)

        self.logger.info("disconnected_from_elevenlabs")

    async def send_text(self, text: str, flush: bool = True) -> None:
        """Send text to be converted to speech.

        Args:
            text: Text to convert to speech
            flush: Whether to flush the buffer (generate audio immediately)
        """
        if not self.ws or not self._connected:
            self.logger.warning("elevenlabs_not_connected")
            return

        try:
            message: dict[str, Any] = {"text": text}

            # Flush to generate audio immediately
            if flush:
                message["flush"] = True

            # Mark send time so the receive loop can observe first-byte
            # latency. Only record if we don't already have a pending
            # observation to avoid resetting the clock mid-utterance.
            if self._pending_send_text_at is None:
                self._pending_send_text_at = time.monotonic()

            await self.ws.send(json.dumps(message))
            self.logger.debug(
                "elevenlabs_text_sent",
                text_length=len(text),
                flush=flush,
            )

        except Exception as e:
            self.logger.exception("elevenlabs_send_text_error", error=str(e))

    async def _handle_message(
        self,
        message: str | bytes,
        stats: dict[str, int],
    ) -> None:
        """Decode a single ElevenLabs WS message and route it.

        Extracted from :meth:`_receive_audio_loop` so the loop body stays
        small enough to read — the loop's job is connection lifecycle
        (disconnect detection + reconnect), not per-chunk audio handling.

        ``stats`` is a mutable counters dict (``chunks``, ``bytes``) shared
        with the loop so the progress log lines and ``isFinal`` summary
        survive reconnects within the same session.
        """
        try:
            data = json.loads(message)
        except json.JSONDecodeError as e:
            self.logger.warning("elevenlabs_invalid_json", error=str(e))
            return

        # Audio chunk received
        if "audio" in data and data["audio"]:
            audio_bytes = base64.b64decode(data["audio"])
            stats["chunks"] += 1
            stats["bytes"] += len(audio_bytes)

            # Observe TTS first-byte latency on the first chunk
            # following a send_text() call.
            if self._pending_send_text_at is not None:
                elevenlabs_tts_latency_ms.observe(
                    (time.monotonic() - self._pending_send_text_at) * 1000.0
                )
                self._pending_send_text_at = None

            await self._audio_queue.put(audio_bytes)

            if stats["chunks"] % 50 == 0:
                self.logger.debug(
                    "elevenlabs_audio_progress",
                    chunks=stats["chunks"],
                    total_bytes=stats["bytes"],
                )

        # Check for final message
        if data.get("isFinal"):
            # Clear any unresolved send marker so a follow-up send_text()
            # restarts the latency measurement.
            self._pending_send_text_at = None
            self.logger.info(
                "elevenlabs_stream_complete",
                total_chunks=stats["chunks"],
                total_bytes=stats["bytes"],
            )

        # Handle errors
        if "error" in data:
            self.logger.error("elevenlabs_error", error=data["error"])

    async def _receive_audio_loop(self) -> None:
        """Background task to receive audio from ElevenLabs.

        The outer ``while`` loop owns reconnection: when the inner async-for
        terminates because the peer closed the socket, we delegate to
        :meth:`_reconnect` and resume from a fresh ``self.ws`` if it
        succeeds. Exhaustion (or a tripped circuit breaker) breaks out and
        signals end-of-stream to consumers via ``None`` on the audio queue.
        """
        if not self.ws:
            return

        stats: dict[str, int] = {"chunks": 0, "bytes": 0}

        try:
            while self._connected and self.ws is not None:
                disconnect_reason: str | None = None
                try:
                    async for message in self.ws:
                        await self._handle_message(message, stats)
                    # async-for exited cleanly — peer closed without an
                    # exception (rare with the websockets library, but
                    # treat it as a clean disconnect).
                    disconnect_reason = "connection_closed"
                except ConnectionClosedError as e:
                    # ``rcvd`` is the peer-sent close frame (None if the
                    # peer just dropped); newer websockets versions
                    # deprecate the top-level ``e.code``/``e.reason``
                    # accessors in favour of ``e.rcvd``.
                    rcvd = e.rcvd
                    self.logger.warning(
                        "elevenlabs_connection_closed_error",
                        code=rcvd.code if rcvd is not None else None,
                        reason=rcvd.reason if rcvd is not None else None,
                    )
                    disconnect_reason = "connection_closed_error"
                except ConnectionClosed as e:
                    rcvd = e.rcvd
                    self.logger.warning(
                        "elevenlabs_connection_closed",
                        code=rcvd.code if rcvd is not None else None,
                        reason=rcvd.reason if rcvd is not None else None,
                    )
                    disconnect_reason = "connection_closed"

                # Disconnected — try to reconnect. If reconnect fails (or
                # is gated by the breaker), surface end-of-stream to the
                # caller by breaking out.
                if not await self._reconnect(disconnect_reason):
                    self._connected = False
                    break
                # Reconnect succeeded: loop back and resume reading from
                # the new ``self.ws``.
        except asyncio.CancelledError:
            self.logger.info("elevenlabs_receive_cancelled")
        except Exception as e:
            self.logger.exception("elevenlabs_receive_error", error=str(e))
        finally:
            # Signal end of stream
            await self._audio_queue.put(None)

    async def receive_audio_stream(self) -> AsyncIterator[bytes]:
        """Stream audio chunks from ElevenLabs.

        Yields:
            Audio chunks in ulaw_8000 format (ready for Telnyx)
        """
        while True:
            chunk = await self._audio_queue.get()
            if chunk is None:
                break
            yield chunk

    def is_connected(self) -> bool:
        """Check if connected to ElevenLabs.

        Returns:
            True if connected, False otherwise
        """
        return self._connected and self.ws is not None


def get_voice_id(voice_name: str) -> str:
    """Get ElevenLabs voice ID from voice name.

    Args:
        voice_name: Voice name (e.g., "rachel", "bella")

    Returns:
        Voice ID string
    """
    voice_lower = voice_name.lower()
    if voice_lower in ELEVENLABS_VOICES:
        return ELEVENLABS_VOICES[voice_lower]["id"]

    # Check if it's already a voice ID
    for voice in ELEVENLABS_VOICES.values():
        if voice["id"] == voice_name:
            return voice_name

    # Default to Rachel
    return ELEVENLABS_VOICES["rachel"]["id"]
