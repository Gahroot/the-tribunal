"""Telnyx SMS service for sending and receiving messages."""

import uuid
from datetime import UTC, datetime

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.conversation import Conversation, Message

logger = structlog.get_logger()


class TelnyxSMSService:
    """SMS service for Telnyx messaging.

    Handles:
    - Sending SMS messages
    - Managing conversations
    - Processing inbound messages
    - Tracking delivery status
    """

    BASE_URL = "https://api.telnyx.com/v2"

    def __init__(self, api_key: str) -> None:
        """Initialize SMS service.

        Args:
            api_key: Telnyx API key
        """
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None
        self.logger = logger.bind(service="telnyx_sms")

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

    async def send_message(
        self,
        to_number: str,
        from_number: str,
        body: str,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID | None = None,
        campaign_id: uuid.UUID | None = None,
    ) -> Message:
        """Send an SMS message and store it.

        Args:
            to_number: Recipient phone number (E.164)
            from_number: Sender phone number (E.164)
            body: Message content
            db: Database session
            workspace_id: Workspace ID
            agent_id: Optional agent ID if sent by AI
            campaign_id: Optional campaign ID if part of campaign

        Returns:
            Created Message record
        """
        log = self.logger.bind(to=to_number, from_=from_number)
        log.info("sending_sms")

        # Get or create conversation
        conversation = await self._get_or_create_conversation(
            db=db,
            workspace_phone=from_number,
            contact_phone=to_number,
            workspace_id=workspace_id,
        )

        # Create message record
        message = Message(
            conversation_id=conversation.id,
            direction="outbound",
            channel="sms",
            body=body,
            status="queued",
            agent_id=agent_id,
            is_ai=agent_id is not None,
        )
        db.add(message)
        await db.flush()

        # Send via Telnyx
        try:
            payload: dict[str, str] = {
                "to": to_number,
                "from": from_number,
                "text": body,
                "type": "SMS",
            }

            response = await self.client.post("/messages", json=payload)
            response_data = response.json()

            log.info(
                "telnyx_response",
                status_code=response.status_code,
            )

            if response.status_code in (200, 202):
                data = response_data.get("data", {})
                message.provider_message_id = data.get("id")
                message.status = "sent"
                message.sent_at = datetime.now(UTC)
                log.info("sms_sent", message_id=message.provider_message_id)
            else:
                errors = response_data.get("errors", [])
                error_msg = errors[0].get("detail") if errors else response.text
                message.status = "failed"
                log.error("sms_send_failed", error=error_msg)

        except Exception as e:
            message.status = "failed"
            log.exception("sms_send_exception", error=str(e))

        # Update conversation
        conversation.last_message_preview = body[:255]
        conversation.last_message_at = datetime.now(UTC)

        await db.commit()
        await db.refresh(message)

        return message

    async def process_inbound_message(
        self,
        db: AsyncSession,
        provider_message_id: str,
        from_number: str,
        to_number: str,
        body: str,
        workspace_id: uuid.UUID,
    ) -> Message:
        """Process an inbound SMS message.

        Args:
            db: Database session
            provider_message_id: Telnyx message ID
            from_number: Sender's phone number
            to_number: Our phone number
            body: Message content
            workspace_id: Workspace ID

        Returns:
            Created Message record
        """
        log = self.logger.bind(
            provider_message_id=provider_message_id,
            from_=from_number,
            to=to_number,
        )
        log.info("processing_inbound_sms")

        # Get or create conversation (swap from/to for inbound)
        conversation = await self._get_or_create_conversation(
            db=db,
            workspace_phone=to_number,  # Our number
            contact_phone=from_number,  # Their number
            workspace_id=workspace_id,
        )

        # Create message record
        message = Message(
            conversation_id=conversation.id,
            provider_message_id=provider_message_id,
            direction="inbound",
            channel="sms",
            body=body,
            status="received",
        )
        db.add(message)

        # Update conversation
        conversation.last_message_preview = body[:255]
        conversation.last_message_at = datetime.now(UTC)
        conversation.unread_count += 1

        # Check for opt-out keywords
        opt_out_keywords = ["stop", "unsubscribe", "opt out", "optout", "cancel"]
        if body.lower().strip() in opt_out_keywords:
            conversation.ai_enabled = False
            log.info("contact_opted_out")

        await db.commit()
        await db.refresh(message)

        log.info("inbound_sms_processed", message_id=str(message.id))
        return message

    async def update_message_status(
        self,
        db: AsyncSession,
        provider_message_id: str,
        status: str,
    ) -> Message | None:
        """Update message delivery status.

        Args:
            db: Database session
            provider_message_id: Telnyx message ID
            status: New status

        Returns:
            Updated message or None if not found
        """
        result = await db.execute(
            select(Message).where(Message.provider_message_id == provider_message_id)
        )
        message = result.scalar_one_or_none()

        if not message:
            self.logger.warning("message_not_found", provider_message_id=provider_message_id)
            return None

        # Map Telnyx status to our status
        status_map = {
            "queued": "queued",
            "sending": "sending",
            "sent": "sent",
            "delivered": "delivered",
            "delivery_failed": "failed",
            "sending_failed": "failed",
        }

        message.status = status_map.get(status, status)

        await db.commit()
        await db.refresh(message)

        self.logger.info(
            "message_status_updated",
            message_id=str(message.id),
            status=message.status,
        )

        return message

    async def _get_or_create_conversation(
        self,
        db: AsyncSession,
        workspace_phone: str,
        contact_phone: str,
        workspace_id: uuid.UUID,
    ) -> Conversation:
        """Get or create a conversation for the given phone numbers.

        Args:
            db: Database session
            workspace_phone: Our phone number
            contact_phone: Contact's phone number
            workspace_id: Workspace ID

        Returns:
            Existing or new conversation
        """
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
            channel="sms",
            ai_enabled=True,  # Default to AI enabled
        )
        db.add(conversation)
        await db.flush()

        self.logger.info(
            "conversation_created",
            conversation_id=str(conversation.id),
            contact_id=contact.id if contact else None,
        )

        return conversation
