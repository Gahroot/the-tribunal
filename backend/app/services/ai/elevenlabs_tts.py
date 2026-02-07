"""ElevenLabs Text-to-Speech WebSocket streaming client.

Provides streaming TTS via ElevenLabs WebSocket API with direct ulaw_8000 output
for Telnyx telephony integration (no audio conversion needed).
"""

import asyncio
import base64
import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any

import structlog
import websockets
from websockets.asyncio.client import ClientConnection

logger = structlog.get_logger()

# ElevenLabs available voices (subset of popular voices)
ELEVENLABS_VOICES = {
    "ava": {"id": "gJx1vCzNCD1EQHT212Ls", "name": "Ava", "description": "Natural female"},
    "lisa": {"id": "lRS76KmLyt8TypvcyLlV", "name": "Lisa", "description": "Friendly female"},
    "sarah_eve": {
        "id": "nf4MCGNSdM0hxM95ZBQR", "name": "Sarah Eve", "description": "Expressive female"
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
        "id": "XB0fDUnXU5powFXDhCwa", "name": "Charlotte", "description": "Swedish female"
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

    def __init__(self, api_key: str, voice_id: str = "21m00Tcm4TlvDq8ikWAM") -> None:
        """Initialize ElevenLabs TTS session.

        Args:
            api_key: ElevenLabs API key
            voice_id: Voice ID (default: Rachel)
        """
        self.api_key = api_key
        self.voice_id = voice_id
        self.ws: ClientConnection | None = None
        self.logger = logger.bind(service="elevenlabs_tts")
        self._audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._receive_task: asyncio.Task[None] | None = None
        self._connected = False

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

        try:
            # Build WebSocket URL with parameters
            url = (
                f"{self.BASE_URL}/{self.voice_id}/stream-input"
                f"?model_id={self.MODEL_ID}"
                f"&output_format={output_format}"
            )

            self.ws = await websockets.connect(
                url,
                additional_headers={
                    "xi-api-key": self.api_key,
                },
            )

            # Send initial configuration (Beginning of Stream - BOS)
            bos_message = {
                "text": " ",  # Required space to start
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                },
                "xi_api_key": self.api_key,
            }
            await self.ws.send(json.dumps(bos_message))

            self._connected = True
            self.logger.info("connected_to_elevenlabs")

            # Start background task to receive audio
            self._receive_task = asyncio.create_task(self._receive_audio_loop())

            return True

        except Exception as e:
            self.logger.exception("elevenlabs_connection_failed", error=str(e))
            return False

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

            await self.ws.send(json.dumps(message))
            self.logger.debug(
                "elevenlabs_text_sent",
                text_length=len(text),
                flush=flush,
            )

        except Exception as e:
            self.logger.exception("elevenlabs_send_text_error", error=str(e))

    async def _receive_audio_loop(self) -> None:
        """Background task to receive audio from ElevenLabs."""
        if not self.ws:
            return

        audio_chunks_received = 0
        total_audio_bytes = 0

        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)

                    # Audio chunk received
                    if "audio" in data and data["audio"]:
                        audio_bytes = base64.b64decode(data["audio"])
                        audio_chunks_received += 1
                        total_audio_bytes += len(audio_bytes)

                        await self._audio_queue.put(audio_bytes)

                        if audio_chunks_received % 50 == 0:
                            self.logger.debug(
                                "elevenlabs_audio_progress",
                                chunks=audio_chunks_received,
                                total_bytes=total_audio_bytes,
                            )

                    # Check for final message
                    if data.get("isFinal"):
                        self.logger.info(
                            "elevenlabs_stream_complete",
                            total_chunks=audio_chunks_received,
                            total_bytes=total_audio_bytes,
                        )

                    # Handle errors
                    if "error" in data:
                        self.logger.error(
                            "elevenlabs_error",
                            error=data["error"],
                        )

                except json.JSONDecodeError as e:
                    self.logger.warning(
                        "elevenlabs_invalid_json",
                        error=str(e),
                    )

        except websockets.exceptions.ConnectionClosed as e:
            self.logger.warning(
                "elevenlabs_connection_closed",
                code=e.code,
                reason=e.reason,
            )
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
