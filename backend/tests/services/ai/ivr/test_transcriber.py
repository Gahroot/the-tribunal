"""Tests for WhisperTranscriber - Phase 1 cheap transcription."""

import io
import wave
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ai.ivr.transcriber import MIN_AUDIO_BYTES, WhisperTranscriber, mulaw_to_wav


class TestMulawToWav:
    """Tests for mulaw_to_wav conversion."""

    def test_produces_valid_wav(self):
        """Output should be a valid WAV file."""
        # Create fake mu-law data (silence = 0xFF)
        mulaw_data = bytes([0xFF] * 8000)  # 1 second at 8kHz
        wav_data = mulaw_to_wav(mulaw_data)

        # Should be valid WAV - parse it
        buf = io.BytesIO(wav_data)
        with wave.open(buf, "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2  # 16-bit PCM
            assert wf.getframerate() == 8000
            assert wf.getnframes() == 8000  # 1 second of audio

    def test_empty_input(self):
        """Empty mu-law data should produce valid (empty) WAV."""
        wav_data = mulaw_to_wav(b"")

        buf = io.BytesIO(wav_data)
        with wave.open(buf, "rb") as wf:
            assert wf.getnframes() == 0

    def test_short_input(self):
        """Short mu-law data should still produce valid WAV."""
        mulaw_data = bytes([0xFF] * 160)  # 20ms
        wav_data = mulaw_to_wav(mulaw_data)

        buf = io.BytesIO(wav_data)
        with wave.open(buf, "rb") as wf:
            assert wf.getnframes() == 160


class TestWhisperTranscriber:
    """Tests for WhisperTranscriber.transcribe()."""

    @pytest.fixture
    def transcriber(self):
        """Create a WhisperTranscriber with mocked OpenAI client."""
        with patch("app.services.ai.ivr.transcriber.AsyncOpenAI") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            t = WhisperTranscriber()
            t._client = mock_client
            yield t

    @pytest.mark.asyncio
    async def test_too_short_audio_returns_empty(self, transcriber: WhisperTranscriber):
        """Audio shorter than MIN_AUDIO_BYTES should return empty string."""
        result = await transcriber.transcribe(bytes([0xFF] * (MIN_AUDIO_BYTES - 1)))
        assert result == ""

    @pytest.mark.asyncio
    async def test_empty_audio_returns_empty(self, transcriber: WhisperTranscriber):
        """Empty audio should return empty string."""
        result = await transcriber.transcribe(b"")
        assert result == ""

    @pytest.mark.asyncio
    async def test_successful_transcription(self, transcriber: WhisperTranscriber):
        """Valid audio should be transcribed via Whisper API."""
        transcriber._client.audio = MagicMock()
        transcriber._client.audio.transcriptions = MagicMock()
        transcriber._client.audio.transcriptions.create = AsyncMock(
            return_value="Press 1 for sales."
        )

        audio = bytes([0xFF] * 8000)
        result = await transcriber.transcribe(audio)

        assert result == "Press 1 for sales."
        transcriber._client.audio.transcriptions.create.assert_called_once()

        # Verify the call was made with correct params
        call_kwargs = transcriber._client.audio.transcriptions.create.call_args.kwargs
        assert call_kwargs["model"] == "whisper-1"
        assert call_kwargs["response_format"] == "text"

    @pytest.mark.asyncio
    async def test_api_error_returns_empty(self, transcriber: WhisperTranscriber):
        """API errors should be caught and return empty string."""
        transcriber._client.audio = MagicMock()
        transcriber._client.audio.transcriptions = MagicMock()
        transcriber._client.audio.transcriptions.create = AsyncMock(
            side_effect=Exception("API error")
        )

        audio = bytes([0xFF] * 8000)
        result = await transcriber.transcribe(audio)
        assert result == ""
