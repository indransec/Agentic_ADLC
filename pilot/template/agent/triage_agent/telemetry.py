"""Traces of the pilot (FR-005; research R-10): one span per request, tool and model call, with
the request id and package hash and never the incident text."""

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

TRACER = "triage_agent"


def setup(environment: str, endpoint: str | None) -> None:
    if not endpoint:
        return
    provider = TracerProvider(
        resource=Resource.create({"service.name": f"pilot-triage-{environment}"})
    )
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces"))
    )
    trace.set_tracer_provider(provider)


def tracer() -> trace.Tracer:
    return trace.get_tracer(TRACER)
