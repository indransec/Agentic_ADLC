"""T013: SqlEvidenceProvider over feature 003 records (FR-008 to FR-011)."""

from datetime import timedelta

from adlc.orchestration.interfaces import EvalContext
from adlc.policy.evidence import Evidence, SqlEvidenceProvider
from adlc.policy.values import NOT_AVAILABLE
from adlc.spec_toolkit.registry import SqlSpecRegistry
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, person


def _provider(h: Harness) -> SqlEvidenceProvider:
    return SqlEvidenceProvider(h.app, SqlSpecRegistry(h.app), h.clock)


def _value(h: Harness, source: str, run_id: str) -> object:
    usecase, terminal, _ = run_id.split("/")
    answer = _provider(h).get(source, EvalContext(terminal, "x", run_id, usecase))
    assert isinstance(answer, Evidence), source
    return answer.value


def test_terminal_record_of_the_latest_closed_run(h: Harness) -> None:
    usecase, t5 = walk_to(h, "T5", tier="high")
    t0 = _value(h, "T0", t5)
    assert isinstance(t0, dict)
    assert t0["status"] == "pass"
    assert t0["signed_by"] == ["business_owner-person"] and t0["signed_roles"] == ["business_owner"]
    assert t0["run_version"] == "run-1" and "closed_at" in t0
    assert t0["risk_classification"][0]["tier"] == "medium"
    assert t0["risk_tier"] == "high"  # the emitted value typed in at the T0 pass
    t4 = _value(h, "T4", t5)
    assert isinstance(t4, dict)
    assert t4["bound_to"] == h.agent.base["T3"]["candidate_package"][0]["sha256"]  # T3 package hash
    # 012 R-09: built from the candidate's harness result; none is recorded here (fails closed)
    assert "eval_baseline" not in t4


def test_own_run_is_open_and_missing_terminals_are_not_available(h: Harness) -> None:
    usecase, t1 = walk_to(h, "T1")
    own = _value(h, "T1", t1)
    assert isinstance(own, dict) and own["status"] == "open" and "kpis" in own
    usecase_, terminal, _ = t1.split("/")
    assert _provider(h).get("T3", EvalContext(terminal, "x", t1, usecase_)) is NOT_AVAILABLE


def test_after_rework_the_new_run_is_read(h: Harness) -> None:
    usecase, t1 = walk_to(h, "T1")
    h.service.decide(
        person("product_owner"), t1, "rework", comment="c", root_cause="requirement", reason="r"
    )
    h.drain()
    t1_run2 = h.active(usecase, "T1").run_id
    h.pass_run(t1_run2)
    t2 = h.active(usecase, "T2").run_id
    record = _value(h, "T1", t2)
    assert isinstance(record, dict) and (record["status"], record["run_version"]) == (
        "pass",
        "run-2",
    )


def test_intake_trigger_run_timeline_tier(h: Harness) -> None:
    usecase, t1 = walk_to(h, "T1", tier="low")
    assert _value(h, "intake", t1) == {
        "free_text": "x" * 250,
        "business_owner": "business_owner-person",
        "title": "Claims triage",
    }
    trigger = _value(h, "trigger", t1)
    assert isinstance(trigger, dict) and trigger["evidence"] == f"{usecase}/T0/run-1"
    run = _value(h, "run", t1)
    assert isinstance(run, dict)
    assert (run["rework_count"], run["run_version"], run["risk_tier"], run["mode"]) == (
        0,
        "run-1",
        "low",
        "evolve",
    )
    h.clock.advance(timedelta(hours=5))
    run = _value(h, "run", t1)
    assert isinstance(run, dict) and run["age"] >= timedelta(hours=5)
    timeline = _value(h, "timeline", t1)
    assert isinstance(timeline, dict) and timeline["escalate_after"] == timedelta(days=10)
    assert _value(h, "tier", t1) == {}  # T1 has no tiering block
    assert _provider(h).get("ci", EvalContext("T1", "x", t1, usecase)) is NOT_AVAILABLE


def test_duration_comparison_as_written_in_specs(h: Harness) -> None:
    """FR-011: run.age > timeline.escalate_after compares durations."""
    from adlc.policy.engine import CelPolicyEngine
    from adlc.policy.predicates import load_all

    usecase, t1 = walk_to(h, "T1")
    engine = CelPolicyEngine(_provider(h), load_all())
    ctx = EvalContext("T1", "x", t1, usecase)
    assert not engine.evaluate("run.age > timeline.escalate_after", ctx).passed
    h.clock.advance(timedelta(days=11))
    assert engine.evaluate("run.age > timeline.escalate_after", ctx).passed
