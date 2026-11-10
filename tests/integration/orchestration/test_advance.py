"""T025: automatic steps run outside transactions and are applied with a version check
(research R-02; US1/AC2, AC4, AC5; FR-005 to FR-008, FR-035)."""

from adlc.orchestration.stubs import StubPolicy
from tests.support.orchestration import Harness, harness
from tests.support.pg import PlatformDatabase


def test_steps_and_activity(h: Harness) -> None:
    usecase = h.submit()
    run = h.active(usecase, "T0")
    assert run.state == "awaiting_sign_off"
    assert set(run.artifacts) >= {"risk_classification"}
    assert run.recommendation is not None and run.recommendation["status"] == "pass"
    assert all(c["passed"] for c in run.control_results)
    rows = h.sql(
        "SELECT step, actor_type, outcome FROM run.run_activity WHERE run_id = :r ORDER BY run_activity_id",
        r=run.run_id,
    )
    assert [tuple(r) for r in rows] == [
        ("route", "orchestrator", "opened"),
        ("prerequisites", "orchestrator", "building"),
        ("build", "agent", "checking"),
        ("controls", "orchestrator", "reviewing"),
        ("review", "reviewer", "awaiting_sign_off"),
    ]
    assert h.run(run.run_id).lease_until is None


def test_blocked_until_an_event_arrives(orch_template: PlatformDatabase) -> None:
    policy = StubPolicy({("T1", "PRE-T1-02"): False})
    with harness(orch_template, policy=policy) as h:
        usecase = h.submit()
        h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "low"})
        t1 = h.active(usecase, "T1")
        assert t1.state == "blocked"
        policy.script[("T1", "PRE-T1-02")] = True
        # A second subscribed event for T1 (T0 passes again after a qualification rework is
        # not needed: any subscribed event re-checks a blocked run).
        from adlc.orchestration import ids, store

        with h.app.begin() as conn:
            store.insert_event(
                conn,
                event_id=ids.uuid7(),
                event_type="T0.exception",
                usecase_id=usecase,
                correlation_id=ids.correlation_id(usecase),
                causation_run_id=None,
                payload={},
                now=h.clock.now(),
            )
        h.drain()
        assert h.run(t1.run_id).state == "awaiting_sign_off"
        assert h.run(t1.run_id).received_events[0]["event_type"] == "T0.exception"


def test_failed_control_retries_without_rework(orch_template: PlatformDatabase) -> None:
    policy = StubPolicy({("T0", "CTL-T0-01"): False})
    with harness(orch_template, policy=policy) as h:
        usecase = h.submit()
        run = h.active(usecase, "T0")
        assert run.state == "escalated"
        assert run.escalation_trigger == "retry_limit"
        assert run.auto_retries == 3
        assert run.rework_count == 0
        assert h.agent.calls["T0"] == 4
        failed = h.agent.contexts[-1].failed_controls
        assert failed and failed[0]["id"] == "CTL-T0-01"
