"""T056: operational events follow the pinned T8 event routes (FR-017; US5/AC1, AC2)."""

import pytest

from adlc.orchestration.service import Actor, NotAuthorised, UnknownEvent
from adlc.orchestration.stubs import StubPolicy
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, harness, person
from tests.support.pg import PlatformDatabase

MONITOR = Actor.system("monitor")


def test_unknown_event_and_people(h: Harness) -> None:
    usecase, _ = walk_to(h, "T8")
    with pytest.raises(UnknownEvent):
        h.service.raise_operational_event(MONITOR, usecase, "sunspots", {})
    with pytest.raises(NotAuthorised):
        h.service.raise_operational_event(person("sre"), usecase, "drift", {})


def test_drift_opens_t9(h: Harness) -> None:
    usecase, t8 = walk_to(h, "T8")
    h.service.raise_operational_event(MONITOR, usecase, "drift", {"metric": "accuracy"})
    h.drain()
    t9 = h.active(usecase, "T9")
    assert t9.trigger_event_type == "T8.event.drift"
    assert t9.trigger_context["operational_event"]["metric"] == "accuracy"
    assert t9.trigger_context["causing_run_id"] == t8


def test_safety_breach_records_immediate_actions_and_opens_t5(h: Harness) -> None:
    usecase, t8 = walk_to(h, "T8")
    h.service.raise_operational_event(MONITOR, usecase, "safety_breach", {"severity": "critical"})
    h.drain()
    assert h.active(usecase, "T5").trigger_event_type == "T8.event.safety_breach"
    detail = h.sql(
        "SELECT detail FROM run.run_activity WHERE run_id = :r AND outcome = 'event_route'", r=t8
    )[0][0]
    assert detail["immediate"] == ["reduce_autonomy_or_kill_switch"]


def test_then_event_when_condition_holds(h: Harness) -> None:
    usecase, _ = walk_to(h, "T8")
    h.service.raise_operational_event(MONITOR, usecase, "incident", {"severity": "sev1"})
    h.drain()
    assert h.active(usecase, "T3").trigger_event_type == "T7.rollback"


def test_no_then_event_when_condition_fails(orch_template: PlatformDatabase) -> None:
    policy = StubPolicy({("T8", "then_when:T8.event.incident"): False})
    with harness(orch_template, policy=policy) as h:
        usecase, _ = walk_to(h, "T8")
        h.service.raise_operational_event(MONITOR, usecase, "incident", {"severity": "sev3"})
        h.drain()
        assert (
            h.sql("SELECT count(*) FROM events.outbox_event WHERE event_type = 'T7.rollback'")[0][0]
            == 0
        )
