"""Base service-layer exceptions.

All domain services should raise exceptions from this hierarchy instead of
coupling to web-framework types like ``HTTPException``. API adapters are
responsible for mapping these typed errors to transport-specific responses.
"""

from __future__ import annotations

from typing import Any, ClassVar


class ServiceError(Exception):
    """Base exception for all service-layer errors."""

    default_code: ClassVar[str] = "service_error"

    def __init__(
        self,
        message: str,
        detail: str | None = None,
        *,
        code: str | None = None,
        details: Any | None = None,
    ) -> None:
        self.message = message
        self.code = code or self.default_code
        self.details = details if details is not None else detail
        self.detail = self.details
        super().__init__(message)


class ValidationError(ServiceError):
    """Raised when a business-rule validation fails."""

    default_code: ClassVar[str] = "validation_error"


class AuthenticationError(ServiceError):
    """Raised when caller credentials are missing or invalid."""

    default_code: ClassVar[str] = "authentication_error"


class PermissionDeniedError(ServiceError):
    """Raised when an authenticated caller cannot perform an action."""

    default_code: ClassVar[str] = "permission_denied"


class NotFoundError(ServiceError):
    """Raised when a requested resource does not exist."""

    default_code: ClassVar[str] = "not_found"


class ConflictError(ServiceError):
    """Raised when a request conflicts with the current resource state."""

    default_code: ClassVar[str] = "conflict"


class RateLimitError(ServiceError):
    """Raised when a caller exceeds a service-layer rate limit."""

    default_code: ClassVar[str] = "rate_limit_exceeded"


class ServiceUnavailableError(ServiceError):
    """Raised when an external dependency is not configured or reachable."""

    default_code: ClassVar[str] = "service_unavailable"
