"""Mu-law audio plumbing between Telnyx and an aiortc peer connection.

Telnyx streams G.711 mu-law at 8 kHz, and the Codex realtime route negotiates
PCMU, so both directions are mu-law and no codec conversion is required. What
*is* required is pacing: WebRTC expects frames at a steady 20 ms cadence, while
Telnyx delivers chunks whenever they arrive.

If a peer negotiates a non-PCMU codec, aiortc hands us decoded PCM frames
instead; :func:`iter_mulaw_frames` converts those back to mu-law so the bridge
always receives one format.
"""

from __future__ import annotations

import asyncio
import audioop
import fractions
import time
from collections.abc import Iterator

import structlog
from aiortc.mediastreams import MediaStreamError, MediaStreamTrack
from av import AudioFrame

logger = structlog.get_logger()

SAMPLE_RATE = 8000
FRAME_MS = 20
# 8 kHz * 20 ms = 160 samples; mu-law is 1 byte per sample.
SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS // 1000
BYTES_PER_FRAME = SAMPLES_PER_FRAME
TIME_BASE = fractions.Fraction(1, SAMPLE_RATE)

# Mu-law encoding of PCM silence.
_SILENCE_BYTE = b"\xff"

# Cap buffered caller audio (~2 s). Beyond this the call is already broken and
# stale audio would only add latency.
_MAX_BUFFER_BYTES = BYTES_PER_FRAME * 100


class MuLawRelayTrack(MediaStreamTrack):
    """Outbound track that paces pushed mu-law bytes into 20 ms frames.

    Audio pushed by the bridge is buffered and emitted on a fixed clock.
    Silence is sent when the buffer underruns, which keeps the RTP stream
    continuous so the far end does not treat gaps as the end of a turn.
    """

    kind = "audio"

    def __init__(self) -> None:
        super().__init__()
        self._buffer = bytearray()
        self._timestamp = 0
        self._start: float | None = None
        self._underruns = 0

    def push(self, mulaw: bytes) -> None:
        """Buffer caller audio for delivery.

        Args:
            mulaw: G.711 mu-law bytes at 8 kHz.
        """
        if not mulaw:
            return
        self._buffer.extend(mulaw)
        if len(self._buffer) > _MAX_BUFFER_BYTES:
            overflow = len(self._buffer) - _MAX_BUFFER_BYTES
            del self._buffer[:overflow]
            logger.warning("mulaw_track_buffer_overflow", dropped_bytes=overflow)

    async def recv(self) -> AudioFrame:
        """Produce the next 20 ms frame on a steady clock."""
        if self.readyState != "live":
            raise MediaStreamError

        if self._start is None:
            self._start = time.monotonic()
        else:
            # Frame N is due at _start + N*20ms. ``_timestamp`` is already the
            # sample offset of this frame, so no extra period is added here --
            # doing so would put a constant 20 ms of latency on every call.
            target = self._start + self._timestamp / SAMPLE_RATE
            delay = target - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)

        if len(self._buffer) >= BYTES_PER_FRAME:
            payload = bytes(self._buffer[:BYTES_PER_FRAME])
            del self._buffer[:BYTES_PER_FRAME]
        else:
            payload = bytes(self._buffer).ljust(BYTES_PER_FRAME, _SILENCE_BYTE)
            self._buffer.clear()
            self._underruns += 1
            if self._underruns % 250 == 0:
                logger.debug("mulaw_track_underrun", count=self._underruns)

        # aiortc encodes to PCMU from s16 PCM, so hand back linear samples.
        pcm = audioop.ulaw2lin(payload, 2)
        frame = AudioFrame(format="s16", layout="mono", samples=SAMPLES_PER_FRAME)
        frame.planes[0].update(pcm)
        frame.sample_rate = SAMPLE_RATE
        frame.pts = self._timestamp
        frame.time_base = TIME_BASE

        self._timestamp += SAMPLES_PER_FRAME
        return frame


def iter_mulaw_frames(frame: AudioFrame) -> Iterator[bytes]:
    """Convert an inbound aiortc frame to 8 kHz mu-law chunks.

    PCMU is ranked first in negotiation, so in practice frames already arrive at
    8 kHz mono and only the mu-law encode runs. The resample below is a
    best-effort fallback for other codecs: it starts from a fresh filter state
    each frame, which is audible as slight roughness but keeps the call up.

    Args:
        frame: Frame received from the remote audio track.

    Yields:
        Mu-law bytes at 8 kHz, ready for Telnyx.
    """
    pcm = bytes(frame.planes[0])
    if not pcm:
        return

    sample_rate = frame.sample_rate or SAMPLE_RATE
    channels = len(frame.layout.channels) if frame.layout else 1

    # Packed formats interleave every channel in plane 0; planar formats give
    # one plane per channel, so plane 0 is already a complete mono signal.
    if channels > 1 and len(frame.planes) == 1:
        pcm = audioop.tomono(pcm, 2, 0.5, 0.5)
    if sample_rate != SAMPLE_RATE:
        pcm, _ = audioop.ratecv(pcm, 2, 1, sample_rate, SAMPLE_RATE, None)

    yield audioop.lin2ulaw(pcm, 2)
