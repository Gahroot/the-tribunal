"""Audio buffer manager for Telnyx streaming.

This module provides buffering for audio chunks to meet Telnyx's
minimum chunk size requirements (20ms-30s duration).

At 8kHz mu-law (1 byte per sample):
- 20ms = 160 bytes (minimum)
- 100ms = 800 bytes (recommended for reliability)
"""

import asyncio
from collections.abc import Callable

import structlog

from app.services.audio.codec import TELNYX_MIN_CHUNK_BYTES

logger = structlog.get_logger()


class AudioBufferManager:
    """Manages audio buffering for Telnyx WebSocket streaming.

    Telnyx requires audio chunks to be between 20ms and 30s in duration.
    This class accumulates audio until the minimum size is reached,
    then sends chunks of the optimal size for low latency.

    Features:
    - Accumulates audio until minimum chunk size
    - Supports interruption (barge-in) to clear buffer
    - Tracks statistics for monitoring
    - Flushes remaining audio on stream end

    Attributes:
        min_chunk_bytes: Minimum bytes before sending (default: 160 = 20ms)
        buffer: Accumulated audio bytes
        chunks_sent: Count of chunks sent to Telnyx
        total_bytes_sent: Total bytes sent to Telnyx
    """

    def __init__(
        self,
        min_chunk_bytes: int = TELNYX_MIN_CHUNK_BYTES,
        send_callback: Callable[[bytes], None] | None = None,
    ) -> None:
        """Initialize audio buffer manager.

        Args:
            min_chunk_bytes: Minimum buffer size before sending (default: 160)
            send_callback: Optional async callback to send audio chunks
        """
        self.min_chunk_bytes = min_chunk_bytes
        self._send_callback = send_callback
        self._buffer = bytearray()
        self._lock = asyncio.Lock()
        self.logger = logger.bind(service="audio_buffer")

        # Statistics
        self.chunks_sent = 0
        self.total_bytes_sent = 0
        self.chunks_received = 0
        self.total_bytes_received = 0

    @property
    def buffer_size(self) -> int:
        """Get current buffer size in bytes."""
        return len(self._buffer)

    async def add_audio(self, audio_data: bytes) -> list[bytes]:
        """Add audio to buffer and return chunks ready to send.

        Accumulates audio until the minimum chunk size is reached,
        then returns chunks of the minimum size.

        Args:
            audio_data: Audio bytes to buffer

        Returns:
            List of audio chunks ready to send (may be empty)
        """
        if not audio_data:
            return []

        self.chunks_received += 1
        self.total_bytes_received += len(audio_data)

        ready_chunks: list[bytes] = []

        async with self._lock:
            self._buffer.extend(audio_data)

            # Extract chunks when we have enough data
            while len(self._buffer) >= self.min_chunk_bytes:
                chunk = bytes(self._buffer[: self.min_chunk_bytes])
                del self._buffer[: self.min_chunk_bytes]
                ready_chunks.append(chunk)

                self.chunks_sent += 1
                self.total_bytes_sent += len(chunk)

        # Log periodically
        if self.chunks_sent > 0 and self.chunks_sent % 100 == 0:
            self.logger.debug(
                "buffer_stats",
                chunks_sent=self.chunks_sent,
                total_bytes_sent=self.total_bytes_sent,
                buffer_size=len(self._buffer),
            )

        return ready_chunks

    async def flush(self) -> bytes | None:
        """Flush any remaining audio in the buffer.

        Call this when the stream ends to send any remaining audio
        that hasn't reached the minimum chunk size.

        Returns:
            Remaining audio bytes, or None if buffer is empty
        """
        async with self._lock:
            if not self._buffer:
                return None

            remaining = bytes(self._buffer)
            self._buffer.clear()

            self.chunks_sent += 1
            self.total_bytes_sent += len(remaining)

            self.logger.debug(
                "buffer_flushed",
                remaining_bytes=len(remaining),
                total_chunks_sent=self.chunks_sent,
            )

            return remaining

    async def clear(self) -> int:
        """Clear the buffer (for interruption/barge-in handling).

        Call this when the user starts speaking to immediately
        stop sending AI audio.

        Returns:
            Number of bytes cleared from buffer
        """
        async with self._lock:
            cleared_bytes = len(self._buffer)
            self._buffer.clear()

            if cleared_bytes > 0:
                self.logger.info(
                    "buffer_cleared_on_interruption",
                    cleared_bytes=cleared_bytes,
                )

            return cleared_bytes

    def get_stats(self) -> dict[str, int]:
        """Get buffer statistics.

        Returns:
            Dictionary with buffer statistics
        """
        return {
            "chunks_received": self.chunks_received,
            "total_bytes_received": self.total_bytes_received,
            "chunks_sent": self.chunks_sent,
            "total_bytes_sent": self.total_bytes_sent,
            "buffer_size": len(self._buffer),
        }

    def reset_stats(self) -> None:
        """Reset statistics counters."""
        self.chunks_sent = 0
        self.total_bytes_sent = 0
        self.chunks_received = 0
        self.total_bytes_received = 0


class InterruptibleAudioBuffer(AudioBufferManager):
    """Audio buffer with interruption event integration.

    Extends AudioBufferManager to automatically clear the buffer
    when an interruption event is set (barge-in detected).
    """

    def __init__(
        self,
        interruption_event: asyncio.Event | None = None,
        min_chunk_bytes: int = TELNYX_MIN_CHUNK_BYTES,
    ) -> None:
        """Initialize interruptible audio buffer.

        Args:
            interruption_event: Event that signals user interruption
            min_chunk_bytes: Minimum buffer size before sending
        """
        super().__init__(min_chunk_bytes=min_chunk_bytes)
        self._interruption_event = interruption_event

    def set_interruption_event(self, event: asyncio.Event) -> None:
        """Set the interruption event.

        Args:
            event: Event that signals user interruption
        """
        self._interruption_event = event

    async def add_audio(self, audio_data: bytes) -> list[bytes]:
        """Add audio with interruption checking.

        Checks for interruption before processing and clears
        buffer if interrupted.

        Args:
            audio_data: Audio bytes to buffer

        Returns:
            List of audio chunks ready to send (empty if interrupted)
        """
        # Check for interruption
        if self._interruption_event and self._interruption_event.is_set():
            await self.clear()
            self._interruption_event.clear()
            return []

        return await super().add_audio(audio_data)
