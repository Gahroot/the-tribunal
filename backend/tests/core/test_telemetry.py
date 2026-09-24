"""OTLP configuration and real protobuf export to a loopback collector."""

from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from unittest.mock import MagicMock

import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core import telemetry


@pytest.mark.parametrize("protocol", ["http/protobuf", "grpc"])
def test_signal_specific_endpoint_and_protocol(monkeypatch, protocol):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://localhost:4318/v1/traces")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", protocol)
    monkeypatch.setattr(telemetry, "_configured", False)
    http_exporter, grpc_exporter = MagicMock(), MagicMock()
    monkeypatch.setattr(telemetry, "HTTPSpanExporter", http_exporter)
    monkeypatch.setattr(telemetry, "OTLPSpanExporter", grpc_exporter)
    monkeypatch.setattr(telemetry, "BatchSpanProcessor", MagicMock())
    monkeypatch.setattr(telemetry, "TracerProvider", MagicMock())
    monkeypatch.setattr(telemetry.trace, "set_tracer_provider", MagicMock())
    assert telemetry.is_enabled()
    assert telemetry.configure_tracing()
    assert http_exporter.call_count == int(protocol == "http/protobuf")
    assert grpc_exporter.call_count == int(protocol == "grpc")


def test_real_http_export_of_call_and_generation(monkeypatch):
    from app.services.ai import call_tracing

    received = []

    class Collector(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append((self.path, ExportTraceServiceRequest.FromString(body)))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Collector)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    provider = TracerProvider()
    try:
        exporter = telemetry.HTTPSpanExporter(
            endpoint=f"http://127.0.0.1:{server.server_port}/api/public/otel/v1/traces",
            headers={},
            timeout=2,
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        monkeypatch.setattr(call_tracing, "_TRACER", provider.get_tracer("test.calls"))
        with (
            call_tracing.call_span("exported-call", "voice.call"),
            call_tracing.measure_first_audio(),
        ):
            turns = call_tracing.ResponseSpans("openai", "realtime")
            turns.start({"id": "r1"})
            turns.finish({"id": "r1", "status": "completed"}, "0.01")
            call_tracing.record_first_audio()
        assert provider.force_flush(timeout_millis=3000)
        assert received[0][0] == "/api/public/otel/v1/traces"
        spans = [
            span
            for _, request in received
            for resource in request.resource_spans
            for scope in resource.scope_spans
            for span in scope.spans
        ]
        assert {span.name for span in spans} == {"voice.call", "voice.llm"}
        assert len({span.trace_id for span in spans}) == 1
        generation = next(span for span in spans if span.name == "voice.llm")
        attrs = {attr.key: attr.value for attr in generation.attributes}
        assert attrs["langfuse.observation.type"].string_value == "generation"
        assert attrs["langfuse.observation.cost_details"].string_value == '{"total": 0.01}'
    finally:
        provider.shutdown()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
