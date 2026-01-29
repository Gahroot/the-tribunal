"""Audio processing services for voice communications.

This package provides audio format conversion and buffering services
for the voice bridge, handling the different audio requirements of
Telnyx (PSTN) and AI voice providers (OpenAI, Grok, ElevenLabs).

Modules:
    codec: Audio format conversion (mulaw, PCM, resampling)
    buffer: Audio buffering for Telnyx chunk size requirements
"""

from app.services.audio.buffer import AudioBufferManager
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

__all__ = [
    # Constants
    "TELNYX_SAMPLE_RATE",
    "OPENAI_SAMPLE_RATE",
    "TELNYX_MIN_CHUNK_BYTES",
    # Enums
    "AudioFormat",
    # Functions
    "mulaw_to_pcm",
    "pcm_to_mulaw",
    "upsample_8k_to_24k",
    "downsample_24k_to_8k",
    "convert_telnyx_to_openai",
    "convert_openai_to_telnyx",
    # Classes
    "AudioCodecService",
    "AudioBufferManager",
]
