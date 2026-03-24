"""Contact service domain exceptions."""

from app.services.exceptions import NotFoundError, ServiceUnavailableError, ValidationError


class ContactNotFoundError(NotFoundError):
    """Raised when a contact cannot be found."""

    def __init__(self, message: str = "Contact not found") -> None:
        super().__init__(message)


class ContactValidationError(ValidationError):
    """Raised when a contact operation fails validation."""


class ContactPhoneNotConfiguredError(ServiceUnavailableError):
    """Raised when no SMS-enabled phone number is available."""
