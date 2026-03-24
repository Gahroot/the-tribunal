"""Message test service domain exceptions."""

from app.services.exceptions import NotFoundError, ValidationError


class MessageTestNotFoundError(NotFoundError):
    """Raised when a message test cannot be found."""

    def __init__(self, message: str = "Message test not found") -> None:
        super().__init__(message)


class MessageTestValidationError(ValidationError):
    """Raised when a message test operation fails validation."""


class VariantNotFoundError(NotFoundError):
    """Raised when a test variant cannot be found."""

    def __init__(self, message: str = "Variant not found") -> None:
        super().__init__(message)


class AgentNotFoundError(NotFoundError):
    """Raised when a referenced agent cannot be found."""

    def __init__(self, message: str = "Agent not found") -> None:
        super().__init__(message)
