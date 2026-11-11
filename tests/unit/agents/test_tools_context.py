"""T008: tools get the run's context; KnowledgeTool adds scope and class from the pinned spec;
tools are described to the model (008 research R-02, R-05)."""

from collections.abc import Iterator, Mapping, Sequence
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from adlc.agents.catalogue import AgentCatalogue, AgentDefinition, ToolBinding
from adlc.agents.context import builder_messages, output_instruction
from adlc.agents.knowledge import (
    KnowledgeTool,
    KnowledgeUnavailable,
    Retrieval,
    grounding_scope,
    knowledge_tools,
)
from adlc.agents.tools import FakeTool, ToolContext, ToolGate
from adlc.spec_toolkit.loader import load_bundle
from adlc.spec_toolkit.registry import InMemorySpecRegistry

SPECS = Path(__file__).resolve().parents[3] / "adlc-specs"


@pytest.fixture
def exporter(monkeypatch: pytest.MonkeyPatch) -> Iterator[InMemorySpanExporter]:
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    monkeypatch.setattr(trace, "get_tracer", lambda name: provider.get_tracer(name))
    yield memory
    provider.shutdown()


@cache
def spec(terminal: str) -> Mapping[str, Any]:
    entry = InMemorySpecRegistry.from_bundle(load_bundle(SPECS)).entry(terminal)
    assert entry is not None
    return entry.spec


def ctx(terminal: str = "T0", step: int = 1) -> ToolContext:
    return ToolContext(
        "UC-0001/T0/run-1", "UC-0001", terminal, spec(terminal), attempt=1, step=step
    )


class FakeCaller:
    def __init__(self, reply: Any = None, error: str | None = None, down: bool = False) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.reply, self.error, self.down = reply, error, down

    def __call__(self, source: str, tool: str, arguments: Mapping[str, Any]) -> tuple[bool, Any]:
        self.calls.append((source, tool, dict(arguments)))
        if self.down:
            raise KnowledgeUnavailable(source)
        if self.error:
            return True, self.error
        return False, self.reply


class FakeLog:
    def __init__(self) -> None:
        self.recorded: list[tuple[ToolContext, list[Retrieval]]] = []

    def record(self, context: ToolContext, found: Sequence[Retrieval]) -> list[Retrieval]:
        numbered = [r.with_id(len(self.recorded) * 10 + i + 1) for i, r in enumerate(found)]
        self.recorded.append((context, numbered))
        return numbered

    def for_attempt(self, run_id: str, attempt: int) -> list[Retrieval]:
        return [r for c, rs in self.recorded for r in rs if c.attempt == attempt]


RESULT = {
    "results": [
        {
            "source": "sharepoint",
            "document": "policies/data.md",
            "section": "Claims data",
            "title": "Data policy",
            "snippet": "owned by ops",
            "content_hash": "sha256:" + "a" * 64,
            "data_class": "internal",
            "synthetic": True,
        }
    ],
    "note": "1 results in scope",
}


def test_grounding_scope_comes_from_the_pinned_spec() -> None:
    assert grounding_scope(spec("T0"), "sharepoint") == ["/strategy, /policies"]
    assert grounding_scope(spec("T1"), "sharepoint") == []  # no grounding entry


def test_knowledge_tool_adds_scope_and_class_and_records() -> None:
    caller, log = FakeCaller(RESULT), FakeLog()
    tool = KnowledgeTool("sharepoint", "search", caller, log)
    text = tool.call({"query": "claims data", "limit": 3, "scope": ["/"], "max_class": "x"}, ctx())
    ((source, name, args),) = caller.calls
    assert (source, name) == ("sharepoint", "search")
    assert args == {
        "query": "claims data",
        "limit": 3,
        "scope": ["/strategy, /policies"],
        "max_class": "internal",
    }  # the model cannot set scope or class
    assert "policies/data.md" in text
    ((context, (found,)),) = log.recorded
    assert (found.document, found.section, found.request) == (
        "policies/data.md",
        "Claims data",
        "claims data",
    )
    assert context.step == 1 and found.retrieval_id == 1


def test_no_grounding_means_no_call() -> None:
    caller = FakeCaller(RESULT)
    text = KnowledgeTool("sharepoint", "search", caller, FakeLog()).call({"query": "x"}, ctx("T1"))
    assert caller.calls == [] and "no grounding scope" in text


def test_unavailable_and_errors_reach_the_agent() -> None:
    down = KnowledgeTool("sharepoint", "search", FakeCaller(down=True), FakeLog())
    assert down.call({"query": "x"}, ctx()) == "knowledge source unavailable: sharepoint"
    wrong = KnowledgeTool("sharepoint", "read", FakeCaller(error="out of scope: a.md"), FakeLog())
    assert "out of scope: a.md" in wrong.call({"document": "a.md"}, ctx())


def test_tools_from_bindings_and_descriptions() -> None:
    agent = AgentDefinition(
        "t0-intake-agent",
        "1.1.0",
        "model",
        "reasoning",
        ("t0-intake-agent", "1.0.0"),
        (
            ToolBinding("sharepoint_search", "mcp:sharepoint:read"),
            ToolBinding("sharepoint_read", "mcp:sharepoint:read"),
            ToolBinding("other_tool", "read:knowledge_base"),
        ),
    )
    tools = knowledge_tools(AgentCatalogue({agent.id: agent}), FakeCaller(), FakeLog())
    assert sorted(tools) == ["sharepoint_read", "sharepoint_search"]
    search, read = tools["sharepoint_search"], tools["sharepoint_read"]
    assert isinstance(search, KnowledgeTool) and isinstance(read, KnowledgeTool)
    described = search.describe()
    assert described["name"] == "sharepoint_search"
    assert set(described["arguments"]) == {"query", "limit"}  # never scope or class
    assert set(read.describe()["arguments"]) == {"document", "section"}


def test_gate_passes_the_context(tmp_path: Path) -> None:
    class Allow:
        def authorize(self, *args: Any) -> bool:
            return True

    seen: list[Any] = []

    class Spy(FakeTool):
        def call(self, arguments: Mapping[str, Any], context: ToolContext | None = None) -> str:
            seen.append(context)
            return "ok"

    agent = AgentDefinition(
        "a", "1", "model", "reasoning", ("a", "1"), (ToolBinding("spy", "mcp:sharepoint:read"),)
    )
    handler = ToolGate(Allow(), {"spy": Spy()}).handler(  # type: ignore[arg-type]
        "UC-0001/T0/run-1", "UC-0001", "T0", agent, spec=spec("T0"), attempt=2
    )
    handler({"name": "spy", "arguments": {}})
    handler({"name": "spy", "arguments": {}})
    assert [(c.attempt, c.step, c.terminal_id) for c in seen] == [(2, 1, "T0"), (2, 2, "T0")]


def test_the_request_lists_tools_and_citations() -> None:
    tools = [
        {
            "name": "sharepoint_search",
            "description": "Search.",
            "arguments": {"query": "text", "limit": "1-10"},
        }
    ]
    text = output_instruction(spec("T0"), ["raci"], tools)
    assert '{"tool": {"name": ' in text and '"citations"' in text
    assert '"citations"' not in output_instruction(spec("T0"), ["raci"], [])
    assert "sharepoint_search" in tool_section_text(tools)


def tool_section_text(tools: list[dict[str, Any]]) -> str:
    from adlc.agents.context import tools_section

    return tools_section(tools)


def test_builder_messages_take_tools() -> None:
    assert "tools" in builder_messages.__code__.co_varnames


def test_tool_span_names_tool_source_outcome_and_count(exporter: Any) -> None:
    """008 FR-021: the tool span carries the tool, source, outcome and result count, no content."""

    class Allow:
        def authorize(self, *args: Any) -> bool:
            return True

    agent = AgentDefinition(
        "a",
        "1",
        "model",
        "reasoning",
        ("a", "1"),
        (ToolBinding("sharepoint_search", "mcp:sharepoint:read"),),
    )
    tool = KnowledgeTool("sharepoint", "search", FakeCaller(RESULT), FakeLog())
    ToolGate(Allow(), {"sharepoint_search": tool}).call(  # type: ignore[arg-type]
        run_id="UC-0001/T0/run-1",
        usecase_id="UC-0001",
        terminal_id="T0",
        agent=agent,
        name="sharepoint_search",
        arguments={"query": "claims data"},
        spec=spec("T0"),
    )
    (found,) = [s for s in exporter.get_finished_spans() if s.name == "adlc.agent.tool"]
    attrs = dict(found.attributes or {})
    assert (attrs["tool"], attrs["source"], attrs["results"], attrs["outcome"]) == (
        "sharepoint_search",
        "sharepoint",
        1,
        "ok",
    )
    assert all("claims" not in str(v) for v in attrs.values())


def test_row_minimums_come_from_the_controls_and_parameters() -> None:
    """008: a control ``size(<artifact>) >= param.x`` becomes "at least N rows" in the request."""
    text = output_instruction(
        spec("T1"), ["acceptance_and_failure"], [], {"test_scenarios_min": 30}
    )
    assert "acceptance_and_failure (required, at least 30 rows)" in text
    assert "at least" not in output_instruction(spec("T1"), ["acceptance_and_failure"], [], {})
