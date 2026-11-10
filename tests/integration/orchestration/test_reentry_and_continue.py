"""T057: template re-entry and continuous review (FR-018, FR-018b; US5/AC3, AC4)."""

from datetime import timedelta

import pytest

from adlc.orchestration.service import Actor, InvalidDecision
from adlc.orchestration.stubs import StubAgent, StubPolicy
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, harness, person
from tests.support.pg import PlatformDatabase

MONITOR = Actor.system("monitor")


def _t9(h: Harness) -> tuple[str, str]:
    usecase, _ = walk_to(h, "T8")
    h.service.raise_operational_event(MONITOR, usecase, "drift", {})
    h.drain()
    return usecase, h.active(usecase, "T9").run_id


def test_reentry_from_artifacts(orch_template: PlatformDatabase) -> None:
    agent = StubAgent({"T9": {1: {"change_impact_assessment": {"reentry_terminal": "T2"}}}})
    with harness(orch_template, agent=agent) as h:
        usecase, t9 = _t9(h)
        h.pass_run(t9)
        assert (
            h.sql("SELECT event_type FROM events.outbox_event WHERE causation_run_id = :r", r=t9)[
                0
            ][0]
            == "T9.reentry.T2"
        )
        t2 = h.active(usecase, "T2")
        assert (t2.run_number, t2.trigger_event_type) == (2, "T9.reentry.T2")


def test_reentry_must_be_a_change_class_terminal(orch_template: PlatformDatabase) -> None:
    """With the real engine, control CTL-T9-01 catches it before anyone decides (004)."""
    bad = {"change_impact_assessment": {"reentry_terminal": "T5"}}
    with harness(orch_template, agent=StubAgent({"T9": {n: bad for n in range(1, 5)}})) as h:
        _, t9 = _t9(h)
        run = h.run(t9)
        assert (run.state, run.escalation_trigger) == ("escalated", "retry_limit")
        failed = [c for c in run.control_results if not c["passed"]]
        assert failed[0]["id"] == "CTL-T9-01"
        assert "re-entry T5 is later than T2" in failed[0]["reason"]


def test_service_refuses_a_bad_reentry_too(orch_template: PlatformDatabase) -> None:
    """The service keeps its own check (defence in depth), shown with a permissive stub policy."""
    agent = StubAgent({"T9": {1: {"change_impact_assessment": {"reentry_terminal": "T5"}}}})
    with harness(orch_template, agent=agent, policy=StubPolicy()) as h:
        _, t9 = _t9(h)
        with pytest.raises(InvalidDecision, match="re-entry"):
            h.service.decide(person("product_owner"), t9, "pass")


def test_alternative_closes_the_lifecycle(h: Harness) -> None:
    usecase, t9 = _t9(h)
    with pytest.raises(InvalidDecision, match="alternative"):
        h.service.decide(person("product_owner"), t9, "pass", fields={"alternative": "itsm"})
    h.service.decide(
        person("product_owner"), t9, "pass", fields={"alternative": "lifecycle_closed"}
    )
    h.drain()
    assert h.service.get_usecase(usecase).status == "closed"
    assert all(r.state == "closed" for r in h.runs(usecase))  # the T8 run closed with it


def test_continue_opens_the_next_review(h: Harness) -> None:
    usecase, t8 = walk_to(h, "T8")
    h.pass_run(t8)
    timers = h.sql(
        "SELECT kind, due_at FROM run.timer WHERE run_id = :r AND cancelled_at IS NULL", r=t8
    )
    assert [t[0] for t in timers] == ["review_due"]
    assert timers[0][1] - h.run(t8).closed_at == timedelta(days=14)  # medium: fortnightly
    h.clock.advance(timedelta(days=13))
    h.drain()
    assert [r.run_id for r in h.runs(usecase) if r.terminal_id == "T8"] == [t8]
    h.clock.advance(timedelta(days=2))
    h.drain()
    review2 = h.active(usecase, "T8")
    assert review2.run_number == 2 and review2.trigger_event_type == "T8.pass"
    assert review2.state == "awaiting_sign_off"
