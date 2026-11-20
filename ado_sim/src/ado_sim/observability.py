"""Request logs and optional traces (research R-12, FR-024).

One log line per request: method, operation (the route template, never values), identity
unique name, status and duration. Field values, comment text, query text and tokens are never
logged. Traces go to an OTLP endpoint (Phoenix) only when ``ADO_SIM_OTLP_ENDPOINT`` is set.
"""

from __future__ import annotations

import logging

from opentelemetry.trace import Tracer

LOGGER_NAME = "ado_sim.requests"
_logger = logging.getLogger(LOGGER_NAME)


def configure_logging(level: str) -> None:
    root = logging.getLogger("ado_sim")
    root.setLevel(level)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root.addHandler(handler)


def log_request(
    method: str, operation: str, identity: str, status: int, duration_ms: float
) -> None:
    _logger.info(
        "request method=%s operation=%s identity=%s status=%d duration_ms=%.1f",
        method,
        operation,
        identity,
        status,
        duration_ms,
    )


def make_tracer(endpoint: str | None) -> Tracer | None:
    """A tracer exporting to ``<endpoint>/v1/traces`` (project ``ado-sim``), or None."""
    if not endpoint:
        return None
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(
        resource=Resource.create(
            {"service.name": "ado-sim", "openinference.project.name": "ado-sim"}
        )
    )
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces"))
    )
    return provider.get_tracer("ado_sim")
