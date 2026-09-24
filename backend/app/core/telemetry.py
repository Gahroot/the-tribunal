"""OpenTelemetry tracing setup.

Initializes a global :class:`TracerProvider` with an OTLP HTTP or gRPC exporter and
auto-instruments the libraries that produce the most useful spans for this
codebase: FastAPI (HTTP server), httpx (outbound HTTP), SQLAlchemy (Postgres),
and redis (cache + queue).

Activation requires ``OTEL_EXPORTER_OTLP_ENDPOINT`` or the signal-specific
``OTEL_EXPORTER_OTLP_TRACES_ENDPOINT``. Without either, local development won't
ship spans to a non-existent collector. When set (e.g. to a Honeycomb / Tempo /
Datadog OTLP endpoint), spans are batched and exported in the background.

The actual instrumentation of FastAPI and SQLAlchemy is wired up in
:mod:`app.main` because both require the live ``app`` / ``engine`` instance;
this module exposes :func:`configure_tracing` for the provider/exporter bits
and :func:`instrument_app` for the per-instance hooks.
"""

from __future__ import annotations

import os

import structlog
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as HTTPSpanExporter,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy.ext.asyncio import AsyncEngine

logger = structlog.get_logger()

# Standard OTLP base endpoint; the signal-specific traces endpoint takes precedence.
# Without either endpoint tracing is disabled.
_ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_ENDPOINT"
_SERVICE_NAME_ENV = "OTEL_SERVICE_NAME"
_DEFAULT_SERVICE_NAME = "aicrm-backend"

_configured = False


def is_enabled() -> bool:
    """Return ``True`` if an OTLP endpoint is configured."""
    return bool(_endpoint())


def _endpoint() -> str:
    return (
        os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "").strip()
        or os.environ.get(_ENDPOINT_ENV, "").strip()
    )


def configure_tracing(*, environment: str | None = None) -> bool:
    """Initialize the global :class:`TracerProvider` and OTLP exporter.

    Idempotent: calling more than once is a no-op after the first successful
    install. Returns ``True`` if tracing was activated, ``False`` if the
    endpoint env var was unset (and therefore the module did nothing).
    """
    global _configured
    if _configured:
        return True

    endpoint = _endpoint()
    if not endpoint:
        logger.info(
            "otel_disabled",
            reason="No OTLP trace endpoint configured",
        )
        return False

    service_name = os.environ.get(_SERVICE_NAME_ENV, _DEFAULT_SERVICE_NAME)
    attributes: dict[str, str] = {"service.name": service_name}
    if environment:
        attributes["deployment.environment"] = environment
    commit_sha = os.environ.get("RAILWAY_GIT_COMMIT_SHA")
    if commit_sha:
        attributes["service.version"] = commit_sha

    resource = Resource.create(attributes)
    provider = TracerProvider(resource=resource)

    # ``OTLPSpanExporter`` reads endpoint, headers, and credentials from the
    # ``OTEL_EXPORTER_OTLP_*`` env vars by default. Passing no kwargs keeps
    # the configuration surface in the environment where operators expect it.
    # Langfuse ingests OTLP over HTTP at /api/public/otel/v1/traces.
    # Use OTEL_EXPORTER_OTLP_TRACES_ENDPOINT for that exact URL and
    # OTEL_EXPORTER_OTLP_HEADERS for Basic auth; never log credential values.
    protocol = os.environ.get(
        "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL",
        os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc"),
    )
    if protocol not in {"grpc", "http/protobuf"}:
        raise ValueError("OTLP trace protocol must be grpc or http/protobuf")
    exporter = HTTPSpanExporter() if protocol == "http/protobuf" else OTLPSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _configured = True

    logger.info(
        "otel_enabled",
        protocol=protocol,
        service_name=service_name,
    )
    return True


def instrument_app(app: FastAPI, engine: AsyncEngine) -> None:
    """Attach OpenTelemetry instrumentation to the FastAPI app and engine.

    No-op when :func:`configure_tracing` was not activated, so tests and
    local dev (which leave both OTLP endpoint settings unset) don't pay
    the instrumentation overhead.
    """
    if not _configured:
        return

    # FastAPI server spans. ``excluded_urls`` keeps high-volume probes out of
    # the trace stream so they don't dominate sampling budgets at the backend.
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="health,healthz,readyz,metrics",
    )

    # Outbound httpx calls (OpenAI, Telnyx, Cal.com, ElevenLabs, SendGrid).
    HTTPXClientInstrumentor().instrument()

    # SQLAlchemy uses the *sync* driver underneath the async wrapper, so we
    # must hand it ``engine.sync_engine`` rather than the AsyncEngine itself.
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)

    # Redis client (cache + worker queues).
    RedisInstrumentor().instrument()

    logger.info("otel_instrumentation_attached")
