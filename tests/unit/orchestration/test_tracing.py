"""T020: orchestration spans carry run attributes (constitution X)."""

from collections.abc import Iterator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from adlc.orchestration import tracing


@pytest.fixture
def exporter(monkeypatch: pytest.MonkeyPatch) -> Iterator[InMemorySpanExporter]:
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)  # tests disable the SDK by default
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    monkeypatch.setattr(trace, "get_tracer", lambda name: provider.get_tracer(name))
    yield memory
    provider.shutdown()


def test_span_name_and_attributes(exporter: InMemorySpanExporter) -> None:
    with tracing.span(
        "agent", "build", run_id="UC-0001/T1/run-1", usecase_id="UC-0001", terminal_id="T1"
    ):
        pass
    (span,) = exporter.get_finished_spans()
    assert span.name == "adlc.agent.build"
    assert dict(span.attributes or {}) == {
        "run_id": "UC-0001/T1/run-1",
        "usecase_id": "UC-0001",
        "terminal_id": "T1",
    }


def test_missing_attributes_are_left_out(exporter: InMemorySpanExporter) -> None:
    with tracing.span("router", "route", usecase_id="UC-0001"):
        pass
    assert dict(exporter.get_finished_spans()[0].attributes or {}) == {"usecase_id": "UC-0001"}


def test_without_a_provider_spans_are_no_ops() -> None:
    assert trace.get_tracer(tracing.TRACER_NAME) is not None
    with tracing.span("policy", "controls"):
        pass
