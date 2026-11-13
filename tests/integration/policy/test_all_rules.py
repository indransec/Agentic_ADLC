"""T038: every T0–T9 rule over a full lifecycle (SC-001, SC-002, SC-003, SC-008).

The lifecycle walks T0→T8 with synthetic data, and a drift event opens T9, so every terminal has
a run to evaluate its rules against. Each blocking control is then broken in a snapshot of its
evidence, to show it fails with a reason naming what failed.
"""

import copy
import os
import statistics
import time
from collections.abc import Mapping
from typing import Any

import pytest

from adlc.orchestration import spec_view
from adlc.orchestration.interfaces import EvalContext
from adlc.orchestration.service import Actor
from adlc.policy.compiler import compile_rule
from adlc.policy.engine import CelPolicyEngine
from adlc.policy.evidence import Evidence, InMemoryEvidenceProvider
from adlc.policy.factory import build_policy_engine
from adlc.policy.predicates import load_all
from adlc.spec_toolkit.registry import SqlSpecRegistry
from tests.support.lifecycle import walk_to
from tests.support.orchestration import SYNTHETIC, Harness

SOURCES = (
    "run",
    "intake",
    "trigger",
    "timeline",
    "tier",
    "param",
    "waivers",
    "directory",
    "env",
    "ci",
    "sbom",
    "harness",
    "redteam",
    "dlp",
    "telemetry",
    "change",
    "template",
    "dataset",
    "release",
    "portfolio",
    "retirement",
    "observability",  # 012
    "registry",  # 012
)


def _lifecycle(h: Harness) -> dict[str, str]:
    usecase, t8 = walk_to(h, "T8")
    h.service.raise_operational_event(Actor.system("monitor"), usecase, "drift", {"psi": 0.3})
    h.drain()
    runs = {r.terminal_id: r.run_id for r in h.runs(usecase)}  # latest run per terminal
    assert set(runs) == {f"T{n}" for n in range(10)}
    return runs


def _rules(h: Harness, terminal: str, run_id: str) -> list[tuple[str, str, bool]]:
    run = h.run(run_id)
    entry = h.orch.runs.entry(terminal, run.spec_version)
    checks = [*spec_view.prerequisites(entry.spec), *spec_view.controls(entry.spec)]
    return [(c.id, c.expression, c.blocking) for c in checks]


def test_every_rule_evaluates_and_blocking_ones_pass(h: Harness) -> None:
    runs = _lifecycle(h)
    engine = build_policy_engine(h.app, SqlSpecRegistry(h.app), h.clock, synthetic_dir=SYNTHETIC)
    timings: list[float] = []
    count = 0
    for terminal, run_id in sorted(runs.items()):
        usecase = run_id.split("/")[0]
        for check_id, expression, blocking in _rules(h, terminal, run_id):
            ctx = EvalContext(terminal, check_id, run_id, usecase)
            engine.evaluate(expression, ctx)  # warm the program cache
            started = time.perf_counter()
            result = engine.evaluate(expression, ctx)
            timings.append((time.perf_counter() - started) * 1000)
            count += 1
            assert not result.reason.startswith("evaluation error"), (
                check_id,
                result.reason,
            )  # SC-001
            if blocking:
                assert result.passed, (check_id, result.reason)  # SC-002
    assert count == 112
    p95 = statistics.quantiles(timings, n=20)[18]
    print(f"\n98 rules: p95 {p95:.1f} ms, max {max(timings):.1f} ms")
    assert p95 < (100 if os.environ.get("CI") else 50)  # SC-008


# ------------------------------------------------------------------ SC-003: each control can fail


def _snapshot(h: Harness, terminal: str, run_id: str) -> dict[str, Any]:
    engine = build_policy_engine(h.app, SqlSpecRegistry(h.app), h.clock, synthetic_dir=SYNTHETIC)
    ctx = EvalContext(terminal, "snapshot", run_id, run_id.split("/")[0])
    out: dict[str, Any] = {}
    for source in (*SOURCES, *(f"T{n}" for n in range(10))):
        answer = engine.evidence.get(source, ctx)
        if isinstance(answer, Evidence):
            out[source] = copy.deepcopy(answer.value)
    return out


def _break(evidence: dict[str, Any], path: tuple[str, ...]) -> None:
    """Break the value at ``path``: a table loses its cells, anything else is removed."""
    node: Any = evidence
    for member in path[:-1]:
        if isinstance(node, list):
            node = node[0] if node else {}
        node = node.get(member) if isinstance(node, Mapping) else None
        if node is None:
            return
    last = path[-1]
    if isinstance(node, list):
        node = node[0] if node else {}
    if not isinstance(node, dict) or last not in node:
        return
    value = node[last]
    if isinstance(value, list) and value and isinstance(value[0], dict):
        node[last] = [{k: "" for k in row} for row in value]
    else:
        del node[last]


SPECIAL: dict[str, Any] = {
    # Rules whose evidence is not named in the expression itself.
    "CTL-T0-01": lambda ev, t: ev[t].pop("risk_classification"),
    "CTL-T6-01": lambda ev, t: ev["T3"].__setitem__("status", "rework"),
    "CTL-T6-02": lambda ev, t: ev["waivers"].append(
        {"waiver_id": "WVR-0099", "run_id": "x", "expiry": "2026-11-11"}
    ),
    "CTL-T8-01": lambda ev, t: ev["telemetry"]["monitors"].__setitem__("safety", False),
    "CTL-T8-04": lambda ev, t: ev["waivers"].append(
        {"waiver_id": "WVR-0098", "run_id": "x", "expiry": "2020-01-01"}
    ),
    "CTL-T9-02": lambda ev, t: ev[t]["change_impact_assessment"][0].update(
        affected_components="autonomy", change_class="minor"
    ),
    "CTL-T9-03": lambda ev, t: ev[t]["change_impact_assessment"][0].update(
        affected_components="tool", change_class="minor"
    ),
    "CTL-T9-04": lambda ev, t: (
        ev["run"].__setitem__("mode", "retire"),
        ev["retirement"].__setitem__("credentials_revoked", False),
    ),
    "CTL-T9-05": lambda ev, t: (
        ev["run"].__setitem__("mode", "retire"),
        ev["retirement"].__setitem__("data_disposed", False),
    ),
    "CTL-T9-06": lambda ev, t: (
        ev["run"].__setitem__("mode", "retire"),
        ev["retirement"].__setitem__("unowned_dependants", 2),
    ),
    "CTL-T7-07": lambda ev, t: ev[t]["hypercare_log"].append(
        {"incident_id": "I-9", "severity": "sev1", "closed": ""}
    ),
    "CTL-T8-03": lambda ev, t: ev[t]["incident_problem_log"].append(
        {"incident_id": "I-9", "severity": "sev2", "closed": ""}
    ),
    "CTL-T2-05": lambda ev, t: ev[t].__setitem__("hitl_design", [{"action": "other"}]),
    "CTL-T5-06": lambda ev, t: ev[t]["threat_model_results"].append(
        {"threat_id": "TH-9", "residual_risk": "critical", "result": "open"}
    ),
    "CTL-T6-06": lambda ev, t: ev[t].__setitem__(
        "monitoring_readiness", [{"signal": "other", "alert_threshold": "x"}]
    ),
    "CTL-T4-04": lambda ev, t: ev[t]["defect_log"].append(
        {"defect_id": "D-9", "severity": "critical", "status": "open"}
    ),
}


def _fixed(spec: Mapping[str, Any]) -> Any:
    return lambda ctx: spec


def test_each_blocking_control_fails_with_a_named_reason(h: Harness) -> None:
    runs = _lifecycle(h)
    catalogue = SqlSpecRegistry(h.app).catalogue
    checked = 0
    still_passing: list[str] = []
    unnamed: list[tuple[str, str]] = []
    for terminal, run_id in sorted(runs.items()):
        base = _snapshot(h, terminal, run_id)
        for check_id, expression, blocking in _rules(h, terminal, run_id):
            if not blocking or not check_id.startswith("CTL-"):
                continue
            evidence = copy.deepcopy(base)
            if check_id in SPECIAL:
                SPECIAL[check_id](evidence, terminal)
            else:
                for ref in compile_rule(expression).refs:
                    _break(evidence, ref)
            spec = h.orch.runs.entry(terminal, h.run(run_id).spec_version).spec
            engine = CelPolicyEngine(
                InMemoryEvidenceProvider(evidence),
                load_all(),
                catalogue=lambda name: c.content if (c := catalogue(name)) else None,
                spec_for=_fixed(spec),
                clock=h.clock,
            )
            result = engine.evaluate(
                expression, EvalContext(terminal, check_id, run_id, run_id.split("/")[0])
            )
            if result.passed:
                still_passing.append(check_id)
                continue
            named = (
                any(f"T{n}" in result.reason for n in range(10))
                or "evidence not available" in result.reason
            )
            if not (named or result.reason.startswith(("rule is false", "monitors", "waiver"))):
                unnamed.append((check_id, result.reason))
            checked += 1
    assert still_passing == [], f"still pass after breaking: {still_passing}"
    assert unnamed == []
    assert checked == sum(
        1 for t, r in runs.items() for c, _, b in _rules(h, t, r) if b and c.startswith("CTL-")
    )


@pytest.mark.parametrize("unused", [None])
def test_snapshot_sources_cover_every_root(h: Harness, unused: None) -> None:
    roots = {
        root
        for t in range(10)
        for check in (
            *spec_view.prerequisites(h.orch.runs.registry.entry(f"T{t}").spec),  # type: ignore[union-attr]
            *spec_view.controls(h.orch.runs.registry.entry(f"T{t}").spec),  # type: ignore[union-attr]
        )
        for root in compile_rule(check.expression).roots
    }
    assert roots <= {*SOURCES, *(f"T{n}" for n in range(10))}
