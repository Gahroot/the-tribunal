"""Tests for audio codec service.

Tests audio format conversion functions for voice communications.
"""

import pytest

from app.services.ai.exceptions import AudioConversionError
from app.services.audio.codec import (
    OPENAI_SAMPLE_RATE,
    TELNYX_MIN_CHUNK_BYTES,
    TELNYX_SAMPLE_RATE,
    AudioCodecService,
    AudioFormat,
    convert_openai_to_telnyx,
    convert_telnyx_to_openai,
    downsample_24k_to_8k,
    mulaw_to_pcm,
    pcm_to_mulaw,
    upsample_8k_to_24k,
)


class TestConstants:
    """Tests for audio format constants."""

    def test_telnyx_sample_rate(self) -> None:
        """Test Telnyx sample rate is 8kHz."""
        assert TELNYX_SAMPLE_RATE == 8000

    def test_openai_sample_rate(self) -> None:
        """Test OpenAI/Grok sample rate is 24kHz."""
        assert OPENAI_SAMPLE_RATE == 24000

    def test_telnyx_min_chunk_bytes(self) -> None:
        """Test Telnyx minimum chunk size is 160 bytes (20ms)."""
        assert TELNYX_MIN_CHUNK_BYTES == 160


class TestAudioFormat:
    """Tests for AudioFormat enum."""

    def test_mulaw_8k_sample_rate(self) -> None:
        """Test MULAW_8K has 8kHz sample rate."""
        assert AudioFormat.MULAW_8K.sample_rate == 8000

    def test_pcm16_24k_sample_rate(self) -> None:
        """Test PCM16_24K has 24kHz sample rate."""
        assert AudioFormat.PCM16_24K.sample_rate == 24000

    def test_mulaw_is_mulaw(self) -> None:
        """Test is_mulaw property for mu-law formats."""
        assert AudioFormat.MULAW_8K.is_mulaw
        assert AudioFormat.G711_ULAW.is_mulaw
        assert not AudioFormat.PCM16_8K.is_mulaw
        assert not AudioFormat.PCM16_24K.is_mulaw


class TestMulawConversion:
    """Tests for mu-law to/from PCM conversion."""

    def test_mulaw_to_pcm_empty(self) -> None:
        """Test mulaw_to_pcm with empty input."""
        result = mulaw_to_pcm(b"")
        assert result == b""

    def test_mulaw_to_pcm_basic(self) -> None:
        """Test mulaw_to_pcm produces correct output size."""
        # 1 byte mu-law -> 2 bytes PCM16
        mulaw_data = bytes([0x80] * 100)  # 100 bytes of silence in mu-law
        pcm_data = mulaw_to_pcm(mulaw_data)
        assert len(pcm_data) == 200  # 2x bytes for 16-bit samples

    def test_pcm_to_mulaw_empty(self) -> None:
        """Test pcm_to_mulaw with empty input."""
        result = pcm_to_mulaw(b"")
        assert result == b""

    def test_pcm_to_mulaw_basic(self) -> None:
        """Test pcm_to_mulaw produces correct output size."""
        # 2 bytes PCM16 -> 1 byte mu-law
        pcm_data = bytes([0x00] * 200)  # 100 samples of silence
        mulaw_data = pcm_to_mulaw(pcm_data)
        assert len(mulaw_data) == 100

    def test_mulaw_pcm_roundtrip(self) -> None:
        """Test mu-law -> PCM -> mu-law roundtrip."""
        # Note: This is lossy compression, so exact match not expected
        original = bytes([0x7F, 0x80, 0x00, 0xFF] * 10)
        pcm = mulaw_to_pcm(original)
        back = pcm_to_mulaw(pcm)
        assert len(back) == len(original)


class TestResampling:
    """Tests for sample rate conversion."""

    def test_upsample_empty(self) -> None:
        """Test upsampling with empty input."""
        result = upsample_8k_to_24k(b"")
        assert result == b""

    def test_upsample_too_small(self) -> None:
        """Test upsampling with input smaller than 2 bytes."""
        result = upsample_8k_to_24k(b"\x00")
        assert result == b"\x00"

    def test_upsample_produces_more_samples(self) -> None:
        """Test 8kHz to 24kHz upsampling produces ~3x samples."""
        # 100 samples * 2 bytes = 200 bytes at 8kHz
        pcm_8k = bytes([0x00, 0x00] * 100)
        pcm_24k = upsample_8k_to_24k(pcm_8k)
        # Should produce ~300 samples * 2 bytes = ~600 bytes
        assert len(pcm_24k) >= 500  # Allow some tolerance

    def test_downsample_empty(self) -> None:
        """Test downsampling with empty input."""
        result = downsample_24k_to_8k(b"")
        assert result == b""

    def test_downsample_too_small(self) -> None:
        """Test downsampling with input smaller than 2 bytes."""
        result = downsample_24k_to_8k(b"\x00")
        assert result == b"\x00"

    def test_downsample_produces_fewer_samples(self) -> None:
        """Test 24kHz to 8kHz downsampling produces ~1/3 samples."""
        # 300 samples * 2 bytes = 600 bytes at 24kHz
        pcm_24k = bytes([0x00, 0x00] * 300)
        pcm_8k = downsample_24k_to_8k(pcm_24k)
        # Should produce ~100 samples * 2 bytes = ~200 bytes
        assert len(pcm_8k) <= 250  # Allow some tolerance


class TestFullConversion:
    """Tests for full conversion pipelines."""

    def test_telnyx_to_openai(self) -> None:
        """Test Telnyx mu-law to Grok PCM16 conversion."""
        # Create some mu-law data (160 bytes = 20ms at 8kHz)
        mulaw_data = bytes([0x80] * 160)
        pcm_data = convert_telnyx_to_openai(mulaw_data, None)

        # Should be upsampled 3x and converted to 16-bit
        # 160 mu-law samples -> 160 PCM16 8kHz -> ~480 PCM16 24kHz
        assert len(pcm_data) >= 800  # At least 400 samples * 2 bytes

    def test_openai_to_telnyx(self) -> None:
        """Test Grok PCM16 to Telnyx mu-law conversion."""
        # Create PCM16 24kHz data (480 samples = 20ms)
        pcm_data = bytes([0x00, 0x00] * 480)
        mulaw_data = convert_openai_to_telnyx(pcm_data, None)

        # Should be downsampled 3x and converted to mu-law
        # 480 PCM16 samples -> 160 PCM16 8kHz -> 160 mu-law
        assert len(mulaw_data) <= 200  # Allow some tolerance


class TestAudioCodecService:
    """Tests for AudioCodecService class."""

    def test_convert_same_format(self) -> None:
        """Test converting to the same format returns input unchanged."""
        service = AudioCodecService()
        data = b"test audio data"
        result = service.convert_for_provider(
            data, AudioFormat.MULAW_8K, AudioFormat.MULAW_8K
        )
        assert result == data

    def test_convert_mulaw_to_pcm24k(self) -> None:
        """Test full conversion from mu-law 8kHz to PCM16 24kHz."""
        service = AudioCodecService()
        mulaw_data = bytes([0x80] * 160)
        pcm_data = service.convert_for_provider(
            mulaw_data, AudioFormat.MULAW_8K, AudioFormat.PCM16_24K
        )
        assert len(pcm_data) > len(mulaw_data)

    def test_convert_pcm24k_to_mulaw(self) -> None:
        """Test full conversion from PCM16 24kHz to mu-law 8kHz."""
        service = AudioCodecService()
        pcm_data = bytes([0x00, 0x00] * 480)
        mulaw_data = service.convert_for_provider(
            pcm_data, AudioFormat.PCM16_24K, AudioFormat.MULAW_8K
        )
        assert len(mulaw_data) < len(pcm_data)

    def test_convert_unsupported_raises(self) -> None:
        """Test that unsupported conversion raises error."""
        service = AudioCodecService()
        with pytest.raises(AudioConversionError):
            # This conversion path doesn't exist
            service.convert_for_provider(
                b"data", AudioFormat.G711_ULAW, AudioFormat.PCM16_24K
            )

    def test_needs_conversion_openai(self) -> None:
        """Test needs_conversion for OpenAI provider."""
        service = AudioCodecService()
        # OpenAI uses g711_ulaw which matches Telnyx
        assert not service.needs_conversion("openai", "inbound")
        assert not service.needs_conversion("openai", "outbound")

    def test_needs_conversion_grok(self) -> None:
        """Test needs_conversion for Grok provider."""
        service = AudioCodecService()
        # Grok always needs conversion
        assert service.needs_conversion("grok", "inbound")
        assert service.needs_conversion("grok", "outbound")

    def test_needs_conversion_elevenlabs(self) -> None:
        """Test needs_conversion for ElevenLabs provider."""
        service = AudioCodecService()
        # ElevenLabs inbound needs conversion (goes to Grok STT)
        assert service.needs_conversion("elevenlabs", "inbound")
        # ElevenLabs outbound doesn't need conversion (outputs ulaw_8000)
        assert not service.needs_conversion("elevenlabs", "outbound")
