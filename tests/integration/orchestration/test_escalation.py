"""T046: escalation is the orchestrator's alone (FR-013, FR-020 to FR-022; US3)."""

from datetime import timedelta

import pytest

from adlc.orchestration.interfaces import BudgetExceeded
from adlc.orchestration.service import InvalidDecision, NotAuthorised
from adlc.orchestration.stubs import StubAgent, StubPolicy
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, harness, person
from tests.support.pg import PlatformDatabase

PO = person("product_owner")


def _rework_t1(h: Harness, usecase: str) -> str:
    run = h.active(usecase, "T1").run_id
    h.service.decide(PO, run, "rework", comment="again", root_cause="requirement", reason="r")
    h.drain()
    return h.active(usecase, "T1").run_id


def test_rework_limit_opens_escalated(h: Harness) -> None:
    usecase, _ = walk_to(h, "T1")
    for expected in (1, 2, 3):
        run = h.run(_rework_t1(h, usecase))
        assert (run.rework_count, run.state) == (expected, "awaiting_sign_off")
    run5 = h.run(_rework_t1(h, usecase))
    assert (run5.run_number, run5.rework_count, run5.state) == (5, 4, "escalated")
    assert run5.escalation_trigger == "rework_limit"
    assert run5.escalation_destination == "human_completion"
    escalations = h.sql("SELECT payload FROM events.outbox_event WHERE event_type = 'T1.escalate'")
    assert escalations[0][0]["trigger"] == "rework_limit"


def test_timer_escalates_waiting_run_once(h: Harness) -> None:
    usecase, run_id = walk_to(h, "T1")
    h.clock.advance(timedelta(days=10, seconds=1))  # T1 escalate_after: 10d from open
    h.drain()
    run = h.run(run_id)
    assert (run.state, run.escalation_trigger) == ("escalated", "timer")
    h.clock.advance(timedelta(days=30))
    h.drain()
    assert (
        h.sql("SELECT count(*) FROM events.outbox_event WHERE event_type = 'T1.escalate'")[0][0]
        == 1
    )


def test_blocked_run_escalates_on_timer(orch_template: PlatformDatabase) -> None:
    policy = StubPolicy({("T1", "PRE-T1-02"): False})
    with harness(orch_template, policy=policy) as h:
        usecase, run_id = walk_to(h, "T1")
        assert h.run(run_id).state == "blocked"
        h.clock.advance(timedelta(days=11))
        h.drain()
        assert h.run(run_id).escalation_trigger == "timer"


def test_budget_exceeded(orch_template: PlatformDatabase) -> None:
    with harness(orch_template, agent=StubAgent({"T0": {1: BudgetExceeded("tokens")}})) as h:
        usecase = h.submit()
        run = h.active(usecase, "T0")
        assert (run.state, run.escalation_trigger) == ("escalated", "budget")


def test_completion_by_accountable_owner(h: Harness) -> None:
    usecase, _ = walk_to(h, "T1")
    h.clock.advance(timedelta(days=11))
    h.drain()
    run = h.active(usecase, "T1")
    with pytest.raises(NotAuthorised):
        h.service.complete_escalation(person("business_owner"), run.run_id, {})  # R, not A
    h.service.complete_escalation(PO, run.run_id, {"kpis": [{"kpi": "handled by hand"}]})
    done = h.run(run.run_id)
    assert done.state == "awaiting_sign_off"
    assert done.artifacts["kpis"] == [{"kpi": "handled by hand"}]
    assert done.rework_count == 0
    h.pass_run(run.run_id)
    assert h.run(run.run_id).final_status == "pass"


def test_nobody_can_set_escalate(h: Harness) -> None:
    _, run_id = walk_to(h, "T1")
    with pytest.raises(InvalidDecision):
        h.service.decide(PO, run_id, "escalate", reason="r")


def test_escalation_destination_is_recorded(orch_template: PlatformDatabase) -> None:
    policy = StubPolicy({("T6", "PRE-T6-01"): False})
    with harness(orch_template, policy=policy) as h:
        usecase, run_id = walk_to(h, "T6")
        h.clock.advance(timedelta(days=8))  # T6 escalate_after 7d
        h.drain()
        run = h.run(run_id)
        assert run.escalation_destination == "release_board"
        h.service.complete_escalation(person("release_manager"), run_id, {})
        assert h.run(run_id).state == "awaiting_sign_off"
