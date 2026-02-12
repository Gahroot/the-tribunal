"""Cheap batch transcription for Phase 1 IVR gate using OpenAI Whisper."""

from __future__ import annotations

import io
import wave

import structlog
from openai import AsyncOpenAI

from app.core.config import settings
from app.services.audio.codec import mulaw_to_pcm

logger = structlog.get_logger()

# Minimum audio bytes to bother transcribing (~0.5s at 8kHz mu-law)
MIN_AUDIO_BYTES = 4000


def mulaw_to_wav(mulaw_data: bytes) -> bytes:
    """Convert mu-law 8kHz audio to WAV format in-memory.

    Pipeline: mu-law 8kHz -> PCM16 8kHz -> WAV container

    Args:
        mulaw_data: Raw mu-law encoded audio at 8kHz

    Returns:
        WAV file bytes (PCM16, 8kHz, mono)
    """
    pcm_data = mulaw_to_pcm(mulaw_data)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(8000)
        wf.writeframes(pcm_data)

    return buf.getvalue()


class WhisperTranscriber:
    """Batch transcription using OpenAI Whisper API ($0.006/min).

    Used by IVRGate for cheap Phase 1 transcription instead of
    expensive realtime AI providers.
    """

    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._log = logger.bind(service="whisper_transcriber")

    async def transcribe(self, mulaw_audio: bytes) -> str:
        """Transcribe mu-law audio using Whisper API.

        Args:
            mulaw_audio: Raw mu-law 8kHz audio bytes

        Returns:
            Transcript text, or empty string on failure or too-short audio
        """
        if len(mulaw_audio) < MIN_AUDIO_BYTES:
            self._log.debug(
                "audio_too_short_for_transcription",
                bytes=len(mulaw_audio),
                min_bytes=MIN_AUDIO_BYTES,
            )
            return ""

        try:
            wav_data = mulaw_to_wav(mulaw_audio)

            wav_file = io.BytesIO(wav_data)
            wav_file.name = "audio.wav"

            response = await self._client.audio.transcriptions.create(
                model="whisper-1",
                file=wav_file,
                response_format="text",
            )

            transcript = str(response).strip()
            self._log.info(
                "whisper_transcription_complete",
                audio_bytes=len(mulaw_audio),
                transcript_length=len(transcript),
                transcript_preview=transcript[:100],
            )
            return transcript

        except Exception as e:
            self._log.exception("whisper_transcription_failed", error=str(e))
            return ""
