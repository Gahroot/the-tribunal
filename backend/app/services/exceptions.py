"""Base service-layer exceptions.

All domain services should raise exceptions from this hierarchy
instead of coupling to web-framework types like ``HTTPException``.

The API layer is responsible for catching these and converting them
to the appropriate HTTP responses.
"""


class ServiceError(Exception):
    """Base exception for all service-layer errors."""

    def __init__(self, message: str, detail: str | None = None) -> None:
        self.message = message
        self.detail = detail
        super().__init__(message)


class NotFoundError(ServiceError):
    """Raised when a requested resource does not exist."""


class ValidationError(ServiceError):
    """Raised when a business-rule validation fails."""


class ServiceUnavailableError(ServiceError):
    """Raised when an external dependency is not configured or reachable."""
