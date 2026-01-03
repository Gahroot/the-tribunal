"""Telnyx voice service for making and receiving calls."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message

logger = structlog.get_logger()


@dataclass
class CallInfo:
    """Call information from Telnyx."""

    id: str
    call_control_id: str
    state: str  # initiated, ringing, answered, completed, failed
    from_number: str
    to_number: str
    duration: int | None = None
    recording_url: str | None = None


class TelnyxVoiceService:
    """Voice service for Telnyx Call Control API.

    Handles:
    - Initiating outbound calls
    - Answering/hanging up calls
    - Managing call control streams
    - Tracking call state and duration
    """

    BASE_URL = "https://api.telnyx.com/v2"

    def __init__(self, api_key: str) -> None:
        """Initialize voice service.

        Args:
            api_key: Telnyx API key
        """
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None
        self.logger = logger.bind(service="telnyx_voice")

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def initiate_call(
        self,
        to_number: str,
        from_number: str,
        connection_id: str,
        webhook_url: str,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        contact_phone: str | None = None,
        agent_id: uuid.UUID | None = None,
        enable_machine_detection: bool = False,
        campaign_id: uuid.UUID | None = None,
    ) -> Message:
        """Initiate outbound call via Telnyx Call Control API.

        Args:
            to_number: Recipient phone number (E.164)
            from_number: Caller ID phone number (E.164)
            connection_id: Telnyx connection ID for voice routing
            webhook_url: Webhook URL for call events
            db: Database session
            workspace_id: Workspace ID
            contact_phone: Contact's phone number for conversation linking
            agent_id: Optional agent ID if call is agent-assisted
            enable_machine_detection: If True, enables voicemail/machine detection
            campaign_id: Optional campaign ID for tracking

        Returns:
            Created Message record with channel="voice"
        """
        log = self.logger.bind(to=to_number, from_=from_number)
        log.info("initiating_call")

        # Get or create conversation
        conversation = await self._get_or_create_conversation(
            db=db,
            workspace_phone=from_number,
            contact_phone=contact_phone or to_number,
            workspace_id=workspace_id,
        )

        # Create message record for call
        message = Message(
            conversation_id=conversation.id,
            direction="outbound",
            channel="voice",
            body="",  # Voice calls don't have body text
            status="queued",
            agent_id=agent_id,
            is_ai=agent_id is not None,
            campaign_id=campaign_id,
        )
        db.add(message)
        await db.flush()

        # Initiate call via Telnyx
        try:
            payload: dict[str, Any] = {
                "to": to_number,
                "from": from_number,
                "connection_id": connection_id,
                "webhook_url": webhook_url,
                "webhook_url_method": "POST",
                "audio_codec": "ulaw",  # μ-law for PSTN compatibility
            }

            # Enable machine detection for voicemail/answering machine
            if enable_machine_detection:
                payload["answering_machine_detection"] = "detect"
                payload["answering_machine_detection_config"] = {
                    "wait_for_beep_timeout_millis": 3000,  # ms to wait for beep
                    "total_analysis_time_millis": 5000,  # Total analysis time
                }
                log.info("machine_detection_enabled")

            response = await self.client.post("/calls", json=payload)
            response_data = response.json()

            log.info(
                "telnyx_response",
                status_code=response.status_code,
            )

            if response.status_code in (200, 201):
                data = response_data.get("data", {})
                call_id = data.get("id")
                call_control_id = data.get("call_control_id")

                message.provider_message_id = call_control_id  # Store call_control_id
                message.status = "ringing"
                log.info(
                    "call_initiated",
                    call_id=call_id,
                    call_control_id=call_control_id,
                )
            else:
                errors = response_data.get("errors", [])
                error_msg = errors[0].get("detail") if errors else response.text
                message.status = "failed"
                log.error("call_initiation_failed", error=error_msg)

        except Exception as e:
            message.status = "failed"
            log.exception("call_initiation_exception", error=str(e))

        # Update conversation
        conversation.channel = "voice"
        conversation.last_message_preview = "Voice call"
        conversation.last_message_at = datetime.now(UTC)

        await db.commit()
        await db.refresh(message)

        return message

    async def answer_call(
        self,
        call_control_id: str,
    ) -> bool:
        """Answer incoming call.

        Args:
            call_control_id: Telnyx call control ID

        Returns:
            True if successful, False otherwise
        """
        self.logger.info("answering_call", call_control_id=call_control_id)

        try:
            response = await self.client.post(
                f"/calls/{call_control_id}/actions/answer",
            )
            response.raise_for_status()
            self.logger.info("call_answered", call_control_id=call_control_id)
            return True
        except Exception as e:
            self.logger.exception(
                "answer_call_failed",
                call_control_id=call_control_id,
                error=str(e),
            )
            return False

    async def hangup_call(
        self,
        call_control_id: str,
    ) -> bool:
        """Hang up call.

        Args:
            call_control_id: Telnyx call control ID

        Returns:
            True if successful, False otherwise
        """
        self.logger.info("hanging_up_call", call_control_id=call_control_id)

        try:
            response = await self.client.post(
                f"/calls/{call_control_id}/actions/hangup",
            )
            response.raise_for_status()
            self.logger.info("call_hung_up", call_control_id=call_control_id)
            return True
        except Exception as e:
            self.logger.exception(
                "hangup_call_failed",
                call_control_id=call_control_id,
                error=str(e),
            )
            return False

    async def start_streaming(
        self,
        call_control_id: str,
        stream_url: str,
        stream_track: str = "inbound_track",
    ) -> bool:
        """Start bidirectional audio streaming for AI integration.

        Args:
            call_control_id: Telnyx call control ID
            stream_url: WebSocket URL for audio stream
            stream_track: Which audio track to stream (inbound_track, outbound_track, both)

        Returns:
            True if successful, False otherwise
        """
        self.logger.info(
            "starting_stream",
            call_control_id=call_control_id,
            stream_url=stream_url,
        )

        try:
            payload: dict[str, Any] = {
                "stream_url": stream_url,
                "stream_track": stream_track,
            }

            response = await self.client.post(
                f"/calls/{call_control_id}/actions/streaming_start",
                json=payload,
            )
            response.raise_for_status()
            self.logger.info(
                "streaming_started",
                call_control_id=call_control_id,
            )
            return True
        except Exception as e:
            self.logger.exception(
                "start_streaming_failed",
                call_control_id=call_control_id,
                error=str(e),
            )
            return False

    async def stop_streaming(
        self,
        call_control_id: str,
    ) -> bool:
        """Stop audio streaming.

        Args:
            call_control_id: Telnyx call control ID

        Returns:
            True if successful, False otherwise
        """
        self.logger.info("stopping_stream", call_control_id=call_control_id)

        try:
            response = await self.client.post(
                f"/calls/{call_control_id}/actions/streaming_stop",
            )
            response.raise_for_status()
            self.logger.info(
                "streaming_stopped",
                call_control_id=call_control_id,
            )
            return True
        except Exception as e:
            self.logger.exception(
                "stop_streaming_failed",
                call_control_id=call_control_id,
                error=str(e),
            )
            return False

    async def update_message_call_status(
        self,
        db: AsyncSession,
        provider_message_id: str,
        status: str,
        duration_seconds: int | None = None,
        recording_url: str | None = None,
    ) -> Message | None:
        """Update call message status and recording info.

        Args:
            db: Database session
            provider_message_id: Telnyx call_control_id
            status: Call status (initiated, ringing, answered, completed, failed)
            duration_seconds: Call duration if completed
            recording_url: URL to call recording if available

        Returns:
            Updated message or None if not found
        """
        from sqlalchemy import select

        result = await db.execute(
            select(Message).where(Message.provider_message_id == provider_message_id)
        )
        message = result.scalar_one_or_none()

        if not message:
            self.logger.warning(
                "message_not_found",
                provider_message_id=provider_message_id,
            )
            return None

        # Map Telnyx status to our status
        status_map = {
            "initiated": "initiated",
            "ringing": "ringing",
            "answered": "answered",
            "completed": "completed",
            "failed": "failed",
            "busy": "failed",
            "no_answer": "failed",
        }

        message.status = status_map.get(status, status)
        if duration_seconds is not None:
            message.duration_seconds = duration_seconds
        if recording_url:
            message.recording_url = recording_url

        await db.commit()
        await db.refresh(message)

        self.logger.info(
            "call_message_updated",
            message_id=str(message.id),
            status=message.status,
            duration=duration_seconds,
        )

        return message

    async def _get_or_create_conversation(
        self,
        db: AsyncSession,
        workspace_phone: str,
        contact_phone: str,
        workspace_id: uuid.UUID,
    ) -> Conversation:
        """Get or create conversation for voice call.

        Args:
            db: Database session
            workspace_phone: Our phone number
            contact_phone: Contact's phone number
            workspace_id: Workspace ID

        Returns:
            Existing or new conversation
        """
        from sqlalchemy import select

        from app.models.contact import Contact

        # Look for existing conversation
        result = await db.execute(
            select(Conversation).where(
                Conversation.workspace_id == workspace_id,
                Conversation.workspace_phone == workspace_phone,
                Conversation.contact_phone == contact_phone,
            )
        )
        conversation = result.scalar_one_or_none()

        if conversation:
            return conversation

        # Try to find contact by phone number
        contact_result = await db.execute(
            select(Contact).where(
                Contact.workspace_id == workspace_id,
                Contact.phone_number == contact_phone,
            )
        )
        contact = contact_result.scalar_one_or_none()

        # Create new conversation
        conversation = Conversation(
            workspace_id=workspace_id,
            contact_id=contact.id if contact else None,
            workspace_phone=workspace_phone,
            contact_phone=contact_phone,
            channel="voice",
            ai_enabled=True,  # Enable AI for voice calls by default
        )
        db.add(conversation)
        await db.flush()

        self.logger.info(
            "conversation_created",
            conversation_id=str(conversation.id),
            contact_id=contact.id if contact else None,
            channel="voice",
        )

        return conversation
