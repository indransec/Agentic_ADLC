"""Request tracing over OTLP (constitution X; FR-025, FR-026; research R-08).

Spans are exported off the request path by a batch processor. Export failures never reach
requests; they are reported as one WARNING per failure burst. Request and response headers are
not captured, so the ``Authorization`` token is never recorded (FR-015).
"""

import logging
import threading
import time
from collections.abc import Sequence

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult

from adlc.config.settings import Settings

SERVICE_NAME = "adlc-api"
EXCLUDED_URLS = "/health$"
EXPORT_TIMEOUT_SECONDS = 2.0
WARNING_INTERVAL_SECONDS = 60.0

log = logging.getLogger("adlc.tracing")


class WarnOnFailureExporter(SpanExporter):
    """Wraps an exporter: swallows its errors and logs one WARNING per failure burst."""

    def __init__(self, inner: SpanExporter, interval: float = WARNING_INTERVAL_SECONDS) -> None:
        self._inner = inner
        self._interval = interval
        self._last_warning: float | None = None
        self._lock = threading.Lock()

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            result = self._inner.export(spans)
        except Exception:  # any exporter failure must stay away from requests
            result = SpanExportResult.FAILURE
        if result is SpanExportResult.FAILURE:
            self._warn()
        else:
            with self._lock:
                self._last_warning = None
        return result

    def _warn(self) -> None:
        now = time.monotonic()
        with self._lock:
            if self._last_warning is not None and now - self._last_warning < self._interval:
                return
            self._last_warning = now
        log.warning("tracing: span export failed; requests are not affected")

    def shutdown(self) -> None:
        try:
            self._inner.shutdown()
        except Exception:  # shutdown errors are as harmless as export errors
            log.warning("tracing: exporter shutdown failed")

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        try:
            return self._inner.force_flush(timeout_millis)
        except Exception:
            return False


def _otlp_exporter(settings: Settings) -> SpanExporter:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    endpoint = settings.otlp_endpoint.rstrip("/") + "/v1/traces"
    return OTLPSpanExporter(endpoint=endpoint, timeout=EXPORT_TIMEOUT_SECONDS)


def setup_tracing(
    app: FastAPI, settings: Settings, exporter: SpanExporter | None = None
) -> TracerProvider:
    """Instrument ``app``; uses OTLP to ``ADLC_OTLP_ENDPOINT`` unless an exporter is given."""
    provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
    inner = exporter if exporter is not None else _otlp_exporter(settings)
    provider.add_span_processor(BatchSpanProcessor(WarnOnFailureExporter(inner)))
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls=EXCLUDED_URLS,
        http_capture_headers_server_request=[],
        http_capture_headers_server_response=[],
    )
    app.state.tracer_provider = provider
    return provider
