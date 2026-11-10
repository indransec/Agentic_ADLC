"""T048: conditions on approvers, external bodies and follow-on events (US7; FR-018)."""

from adlc.orchestration.interfaces import EvalContext
from adlc.orchestration.service import Actor
from adlc.orchestration.stubs import StubAgent
from adlc.policy.factory import build_policy_engine
from adlc.spec_toolkit.registry import SqlSpecRegistry
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, harness, person
from tests.support.pg import PlatformDatabase

MONITOR = Actor.system("monitor")


def test_plus_approver_follows_the_design_deviation(orch_template: PlatformDatabase) -> None:
    deviation = {"design_conformance": {"deviation": "added a cache"}}
    with harness(orch_template, agent=StubAgent({"T3": {1: deviation}})) as h:
        _, t3 = walk_to(h, "T3")
        h.service.decide(person("engineering_lead"), t3, "pass")
        assert h.run(t3).state == "awaiting_sign_off"  # the architect is still needed
    with harness(orch_template) as h:
        _, t3 = walk_to(h, "T3")
        h.service.decide(person("engineering_lead"), t3, "pass")
        assert h.run(t3).final_status == "pass"


def _notified(h: Harness, run_id: str) -> list[object]:
    return [
        r[0]["bodies"]
        for r in h.sql(
            "SELECT detail FROM run.run_activity WHERE run_id = :r AND outcome = 'notified'",
            r=run_id,
        )
    ]


def test_cab_by_tier(h: Harness) -> None:
    _, t6 = walk_to(h, "T6", tier="low")  # tiering low: cab_required false
    h.pass_run(t6)
    assert _notified(h, t6) == []


def test_cab_at_medium(h: Harness) -> None:
    _, t6 = walk_to(h, "T6", tier="medium")
    h.pass_run(t6)
    assert _notified(h, t6) == [["cab"]]


def test_rollback_follow_on_by_severity(h: Harness) -> None:
    usecase, _ = walk_to(h, "T8")
    h.service.raise_operational_event(MONITOR, usecase, "incident", {"severity": "sev3"})
    h.drain()
    assert (
        h.sql("SELECT count(*) FROM events.outbox_event WHERE event_type = 'T7.rollback'")[0][0]
        == 0
    )
    h.service.raise_operational_event(MONITOR, usecase, "incident", {"severity": "sev1"})
    h.drain()
    assert (
        h.sql("SELECT count(*) FROM events.outbox_event WHERE event_type = 'T7.rollback'")[0][0]
        == 1
    )


def test_fail_safe_directions(h: Harness) -> None:
    usecase, t3 = walk_to(h, "T3")
    engine = build_policy_engine(h.app, SqlSpecRegistry(h.app), h.clock)
    broken = "any_design_deviation(T3.no_such_table)"
    plus = engine.evaluate(broken, EvalContext("T3", "plus:solution_architect", t3, usecase))
    assert plus.passed and plus.reason.startswith("fail-safe: approval required")
    external = engine.evaluate("tier.no_such_flag", EvalContext("T3", "external:cab", t3, usecase))
    assert external.passed and external.reason.startswith("fail-safe")
    follow = engine.evaluate(
        "trigger.severity == 'sev1'", EvalContext("T3", "then_when:T8.event.incident", t3, usecase)
    )
    assert not follow.passed and follow.reason.startswith("fail-safe: no follow-on")
    plain_false = engine.evaluate(
        "1 == 2", EvalContext("T3", "plus:solution_architect", t3, usecase)
    )
    assert not plain_false.passed  # a decided "false" is not overridden
    rows = h.sql(
        "SELECT check_id, fail_safe FROM run.policy_decision WHERE fail_safe ORDER BY policy_decision_id"
    )
    assert [r[0] for r in rows] == [
        "plus:solution_architect",
        "external:cab",
        "then_when:T8.event.incident",
    ]
