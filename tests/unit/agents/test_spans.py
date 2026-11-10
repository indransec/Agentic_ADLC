"""T035: spans carry only allow-listed attributes, never prompt or artifact text (FR-023)."""

from collections.abc import Iterator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from adlc.agents.catalogue import ModelCatalogue
from adlc.agents.fake import FakeGateway, reply
from adlc.agents.gateway import CallIds, ModelRequest
from adlc.agents.telemetry import ALLOWED, MAX_VALUE, set_attributes

SECRET = "PROMPT-OR-ARTIFACT-TEXT-4242"
ENTRY = {
    "input_per_mtok": 1.0,
    "output_per_mtok": 1.0,
    "max_output_tokens": 10,
    "context_tokens": 10_000,
    "max_data_class": "internal",
}
CATALOGUE = ModelCatalogue.from_content(
    {
        "profiles": {
            "default": {
                "reasoning": [
                    {"provider": "anthropic", "model": "anthropic/m1", **ENTRY},
                    {"provider": "openai", "model": "openai/m2", **ENTRY},
                ]
            }
        }
    },
    "default",
    {"internal": 2},
)


@pytest.fixture
def exporter(monkeypatch: pytest.MonkeyPatch) -> Iterator[InMemorySpanExporter]:
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    monkeypatch.setattr(trace, "get_tracer", lambda name: provider.get_tracer(name))
    yield memory
    provider.shutdown()


def test_model_call_spans_have_no_content(exporter: InMemorySpanExporter) -> None:
    gateway = FakeGateway(
        CATALOGUE,
        {
            "anthropic/m1": reply("", outcome="outage", reason="rate_limit"),
            "openai/m2": reply(f'{{"answer": "{SECRET}"}}'),
        },
    )
    request = ModelRequest(
        "reasoning",
        "internal",
        ({"role": "system", "content": SECRET}, {"role": "user", "content": SECRET}),
        100,
        5.0,
        CallIds("UC-0001/T1/run-1", "UC-0001", "T1", "a", "UC-0001/T1/run-1/build/1"),
        None,
        "sha256:" + "f" * 64,
    )
    gateway.complete(request)
    spans = exporter.get_finished_spans()
    assert [s.name for s in spans] == ["adlc.model.call", "adlc.model.call"]
    for s in spans:
        attributes = dict(s.attributes or {})
        assert set(attributes) <= ALLOWED | {"run_id", "usecase_id", "terminal_id"}
        assert all(SECRET not in str(v) for v in attributes.values())
        assert all(len(str(v)) <= MAX_VALUE for v in attributes.values())
    assert dict(spans[1].attributes or {})["fallback"] is True
    assert dict(spans[0].attributes or {})["reason"] == "rate_limit"


def test_allow_list_drops_and_cuts(exporter: InMemorySpanExporter) -> None:
    tracer = trace.get_tracer("t")
    with tracer.start_as_current_span("s") as s:
        set_attributes(s, {"prompt": SECRET, "reason": "x" * 500, "tokens_in": 5, "model": None})
    (span,) = exporter.get_finished_spans()
    attributes = dict(span.attributes or {})
    assert attributes == {"reason": "x" * MAX_VALUE, "tokens_in": 5}
