"""T032: tools are authorized first; clarifications say where the agent looked (US4; FR-019,
FR-020)."""

import json
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from adlc.agents.catalogue import AgentCatalogue
from adlc.agents.fake import FakeGateway, reply
from adlc.agents.gateway import ProviderReply
from adlc.agents.store import SqlCallRecorder
from adlc.agents.tools import FakeTool, ToolOutput, ToolRefused
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, harness
from tests.support.pg import PlatformDatabase

from .support import BUNDLE, GOOD, MODELS, PRIMARY, T1_AGENT

KB = FakeTool("KPI baselines come from the 2026 finance extract")
WRITER = FakeTool("should never run")


def _agents() -> AgentCatalogue:
    agents = []
    for a in BUNDLE.catalogue_data("agents")["agents"]:
        if a["id"] == T1_AGENT:
            a = {
                **a,
                "implementation": "model",
                "prompt": {"id": "common-terminal-reviewer", "version": "1.0.0"},
                "tools": [
                    {"tool": "knowledge_search", "permission": "read:knowledge_base"},
                    {"tool": "ledger_writer", "permission": "write:ledger.T0"},
                ],
            }
        agents.append(a)
    return AgentCatalogue.from_content({"agents": agents})


@pytest.fixture
def gated(orch_template: PlatformDatabase) -> Any:
    opened: list[Any] = []

    def make(answers: Sequence[str]) -> tuple[Harness, FakeGateway]:
        class Late:
            gateway: FakeGateway | None = None

            def complete(self, request: Any) -> Any:
                assert self.gateway is not None
                return self.gateway.complete(request)

        late = Late()
        ctx = harness(
            orch_template,
            gateway=late,
            agents=_agents(),
            tools={"knowledge_search": KB, "ledger_writer": WRITER},
        )
        h = ctx.__enter__()
        opened.append(ctx)

        def script(messages: Sequence[Mapping[str, str]]) -> ProviderReply:
            turn = sum(1 for m in messages if m["role"] == "assistant")
            return reply(answers[min(turn, len(answers) - 1)])

        late.gateway = FakeGateway(MODELS, {PRIMARY: script}, recorder=SqlCallRecorder(h.app))
        return h, late.gateway

    yield make
    for ctx in opened:
        ctx.__exit__(None, None, None)


def _tool(name: str) -> str:
    return json.dumps({"tool": {"name": name, "arguments": {"q": "kpi baseline"}}})


def test_allowed_tool_runs_and_denied_tool_is_refused(gated: Any) -> None:
    KB.calls.clear()
    WRITER.calls.clear()
    h, gateway = gated([_tool("knowledge_search"), _tool("ledger_writer"), GOOD])
    usecase, t1 = walk_to(h, "T1")
    assert h.run(t1).state == "awaiting_sign_off"
    assert KB.calls == [{"q": "kpi baseline"}] and WRITER.calls == []
    builder = [
        c for c in gateway.fake.calls if 'source="checklist"' not in c["messages"][1]["content"]
    ]
    after_kb = builder[1]["messages"][-1]["content"]
    assert (
        after_kb.startswith('<data source="tool:knowledge_search">')
        and "finance extract" in after_kb
    )
    after_writer = builder[2]["messages"][-1]["content"]
    assert (
        "ledger_writer was refused" in after_writer and "denied by write:ledger.T0" in after_writer
    )
    decisions = h.sql(
        "SELECT rule, passed FROM run.policy_decision WHERE run_id = :r AND kind = 'authorize' "
        "ORDER BY policy_decision_id",
        r=t1,
    )
    assert [tuple(d) for d in decisions] == [
        ("read:knowledge_base", True),
        ("write:ledger.T0", False),
    ]


def test_tool_calls_are_run_scoped(gated: Any) -> None:
    h, _ = gated([GOOD])
    usecase, t1 = walk_to(h, "T1")
    assert h.runtime is not None and h.runtime.tools is not None
    agent = _agents().agent(T1_AGENT)
    gate = h.runtime.tools
    own = gate.call(
        run_id=t1,
        usecase_id=usecase,
        terminal_id="T1",
        agent=agent,
        name="knowledge_search",
        arguments={},
    )
    assert isinstance(own, ToolOutput)
    other = gate.call(
        run_id=t1,
        usecase_id=usecase,
        terminal_id="T1",
        agent=agent,
        name="knowledge_search",
        arguments={},
        on_behalf_of=f"{usecase}/T0/run-1",
    )
    assert isinstance(other, ToolRefused) and "out of scope" in other.reason
    unbound = gate.call(
        run_id=t1, usecase_id=usecase, terminal_id="T1", agent=agent, name="shell", arguments={}
    )
    assert isinstance(unbound, ToolRefused) and "not available" in unbound.reason


def test_clarification_must_say_where_it_looked(gated: Any) -> None:
    vague = json.dumps({"clarification": {"questions": ["Which channels?"], "looked_in": []}})
    good = json.dumps(
        {
            "clarification": {
                "questions": ["Which channels?"],
                "looked_in": ["intake", "T0 evidence"],
            }
        }
    )
    h, gateway = gated([vague, good])
    usecase = h.submit()
    h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "medium"})
    t1 = h.active(usecase, "T1")
    assert (t1.state, t1.return_state) == ("awaiting_clarification", "building")
    corrections = [
        c["messages"][-1]["content"]
        for c in gateway.fake.calls
        if c["messages"][-1]["content"].startswith("Your previous answer did not fit")
    ]
    assert len(corrections) == 1 and "looked_in" in corrections[0]
