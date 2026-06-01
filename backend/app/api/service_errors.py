"""Route adapters and handlers for service-layer exceptions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import NoReturn

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.routing import APIRoute
from starlette.responses import JSONResponse, Response

from app.services.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServiceError,
    ServiceUnavailableError,
    ValidationError,
)

_SERVICE_ERROR_STATUS_CODES: tuple[tuple[type[ServiceError], int], ...] = (
    (AuthenticationError, status.HTTP_401_UNAUTHORIZED),
    (PermissionDeniedError, status.HTTP_403_FORBIDDEN),
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (ConflictError, status.HTTP_409_CONFLICT),
    (RateLimitError, status.HTTP_429_TOO_MANY_REQUESTS),
    (ServiceUnavailableError, status.HTTP_503_SERVICE_UNAVAILABLE),
    (ValidationError, status.HTTP_400_BAD_REQUEST),
)


def status_code_for_service_error(exc: ServiceError) -> int:
    """Return the HTTP status code for a typed service-layer error."""
    for error_type, status_code in _SERVICE_ERROR_STATUS_CODES:
        if isinstance(exc, error_type):
            return status_code
    return status.HTTP_500_INTERNAL_SERVER_ERROR


def service_error_payload(exc: ServiceError) -> dict[str, object]:
    """Return the canonical error-response payload for a service-layer error."""
    payload: dict[str, object] = {
        "code": exc.code,
        "message": exc.message,
    }
    if exc.details is not None:
        payload["details"] = exc.details
    return payload


def service_error_to_http_exception(exc: ServiceError) -> HTTPException:
    """Convert a service-layer error into a framework HTTP exception.

    The production ``HTTPException`` handler preserves dict details that already
    carry ``code`` and ``message``, so route-adapted service errors keep their
    typed error code in the canonical API response envelope.
    """
    return HTTPException(
        status_code=status_code_for_service_error(exc),
        detail=service_error_payload(exc),
    )


def raise_service_error(exc: ServiceError) -> NoReturn:
    """Raise a mapped ``HTTPException`` for explicit router ``except`` blocks."""
    raise service_error_to_http_exception(exc) from exc


class ServiceErrorRoute(APIRoute):
    """APIRoute that converts service-layer exceptions at the API boundary."""

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original_route_handler = super().get_route_handler()

        async def service_error_route_handler(request: Request) -> Response:
            try:
                return await original_route_handler(request)
            except ServiceError as exc:
                raise_service_error(exc)

        return service_error_route_handler


def _request_id_for(request: Request) -> str:
    """Return the request ID attached by middleware, if available."""
    return str(getattr(request.state, "request_id", "") or "")


async def service_error_exception_handler(request: Request, exc: ServiceError) -> JSONResponse:
    """Return service-layer errors in the canonical API error envelope."""
    payload = service_error_payload(exc)
    payload["request_id"] = _request_id_for(request)
    return JSONResponse(
        status_code=status_code_for_service_error(exc),
        content=payload,
    )


def install_service_error_handler(app: FastAPI) -> None:
    """Register the canonical service-error handler on a FastAPI app."""
    app.add_exception_handler(ServiceError, service_error_exception_handler)
