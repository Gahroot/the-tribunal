"""Acceptance contract for persisted outbound text attempts."""

from app.models.conversation import Message, MessageStatus
from app.services.exceptions import ServiceUnavailableError


class TextDeliveryError(ServiceUnavailableError):
    """A persisted text attempt was not accepted; history remains available."""

    default_code = "text_delivery_failed"

    def __init__(self, message: Message) -> None:
        self.failed_message = message
        # Never expose arbitrary provider bodies, credentials, or recipient PII.
        super().__init__(
            "The text was not accepted. Check the recipient, "
            "sender configuration and messaging permissions before retrying.",
            details={"message_id": str(message.id)},
        )


def require_text_accepted(message: Message) -> Message:
    """Do not confuse a stored failure with an accepted outbound message."""
    if message.status not in {
        MessageStatus.SENDING,
        MessageStatus.SENT,
        MessageStatus.DELIVERED,
    }:
        raise TextDeliveryError(message)
    return message
