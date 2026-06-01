"""Tests for service-layer exception to HTTP response mapping."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import APIRouter, FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.api.service_errors import ServiceErrorRoute, install_service_error_handler
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


@asynccontextmanager
async def _test_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield


@pytest.mark.parametrize(
    ("error", "status_code", "code", "message"),
    [
        (ValidationError("Invalid state"), 400, "validation_error", "Invalid state"),
        (AuthenticationError("Login required"), 401, "authentication_error", "Login required"),
        (PermissionDeniedError("Forbidden"), 403, "permission_denied", "Forbidden"),
        (NotFoundError("Missing row"), 404, "not_found", "Missing row"),
        (ConflictError("Duplicate"), 409, "conflict", "Duplicate"),
        (RateLimitError("Slow down"), 429, "rate_limit_exceeded", "Slow down"),
        (
            ServiceUnavailableError("Provider unavailable"),
            503,
            "service_unavailable",
            "Provider unavailable",
        ),
        (
            ServiceError("Unexpected service error"),
            500,
            "service_error",
            "Unexpected service error",
        ),
    ],
)
async def test_global_handler_maps_service_errors_to_canonical_payload(
    error: ServiceError,
    status_code: int,
    code: str,
    message: str,
) -> None:
    app = FastAPI(lifespan=_test_lifespan)
    install_service_error_handler(app)

    @app.get("/boom")
    async def boom(request: Request) -> None:
        request.state.request_id = "req_test"
        raise error

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/boom")

    assert response.status_code == status_code
    assert response.json() == {
        "code": code,
        "message": message,
        "request_id": "req_test",
    }


async def test_global_handler_includes_details_when_supplied() -> None:
    app = FastAPI(lifespan=_test_lifespan)
    install_service_error_handler(app)

    @app.get("/boom")
    async def boom(request: Request) -> None:
        request.state.request_id = "req_detail"
        raise ValidationError(
            "Invalid filters",
            code="invalid_filters",
            details={"field": "filters"},
        )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/boom")

    assert response.status_code == 400
    assert response.json() == {
        "code": "invalid_filters",
        "message": "Invalid filters",
        "details": {"field": "filters"},
        "request_id": "req_detail",
    }


async def test_route_adapter_maps_service_error_without_global_handler() -> None:
    router = APIRouter(route_class=ServiceErrorRoute)

    @router.get("/missing")
    async def missing() -> None:
        raise NotFoundError("Widget not found")

    app = FastAPI(lifespan=_test_lifespan)
    app.include_router(router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {
        "detail": {
            "code": "not_found",
            "message": "Widget not found",
        }
    }
