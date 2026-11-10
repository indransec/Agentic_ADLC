"""T046: an allow/deny matrix over the real T0–T9 authorities (SC-006), with decision records.

Kept as a unit test: the decision needs only the pinned spec, so it runs without a database.
"""

from typing import Any

import pytest

from adlc.orchestration import spec_view
from adlc.orchestration.interfaces import EvalContext
from adlc.policy.engine import CelPolicyEngine
from adlc.policy.evidence import InMemoryEvidenceProvider
from adlc.policy.predicates import load_all
from adlc.policy.store import MemorySink


def _engine(registry: Any, sink: MemorySink) -> CelPolicyEngine:
    return CelPolicyEngine(
        InMemoryEvidenceProvider({}),
        load_all(),
        spec_for=lambda ctx: registry.entry(ctx.terminal_id).spec,
        sink=sink,
    )


@pytest.mark.parametrize("terminal", [f"T{n}" for n in range(10)])
def test_matrix(registry: Any, terminal: str) -> None:
    sink = MemorySink()
    engine = _engine(registry, sink)
    run = f"UC-0001/{terminal}/run-1"
    ctx = EvalContext(terminal, "authorize", run, "UC-0001")
    authorities = spec_view.body(registry.entry(terminal).spec)["authorities"]
    actor = f"agent:{run}"
    allowed = authorities["allow"][0]
    verb, _, resource = allowed.partition(":")
    assert engine.authorize(actor, verb, resource.replace(".all", ".x"), ctx), allowed
    if authorities.get("deny"):
        denied = authorities["deny"][0].replace("*", "x")
        verb, _, resource = denied.partition(":")
        ok, reason = engine.authorize_decision(actor, verb, resource, ctx)
        assert (ok, reason.startswith("denied by")) == (False, True), denied
    assert not engine.authorize(actor, "zzz", "nothing", ctx)
    if authorities.get("tool_scopes"):
        tool = authorities["tool_scopes"][0].replace("*", "x")
        verb, _, resource = tool.partition(":")
        assert engine.authorize(actor, verb, resource, ctx), tool
    assert not engine.authorize(f"agent:UC-0002/{terminal}/run-1", "read", "x", ctx)
    assert all(d.kind == "authorize" and d.actor for d in sink.decisions)
    assert len(sink.decisions) >= 3
