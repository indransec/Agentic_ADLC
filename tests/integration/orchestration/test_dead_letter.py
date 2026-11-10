"""T062: retries with increasing delays, dead letter after 5, re-queue (SC-006; US6/AC4, AC5)."""

from datetime import timedelta

import pytest

from adlc.orchestration.service import NotAuthorised, NotDeadLettered
from adlc.orchestration.store import EventRow
from tests.support.orchestration import harness, person
from tests.support.pg import PlatformDatabase

COE = person("adlc_coe")


class Fault:
    def __init__(self) -> None:
        self.failing: set[str] = {"usecase.submitted"}

    def __call__(self, event: EventRow) -> None:
        if event.event_type in self.failing:
            raise RuntimeError("router down " + "x" * 5000)


def test_retries_then_dead_letter_then_requeue(orch_template: PlatformDatabase) -> None:
    fault = Fault()
    with harness(orch_template, fault=fault) as h:
        usecase = h.service.submit_usecase(person("business_owner"), "case", "x" * 250)
        delays = []
        for attempt in range(1, 6):
            h.drain()
            row = h.sql(
                "SELECT attempts, next_attempt_at, dead_lettered_at, last_error FROM events.outbox_event"
            )[0]
            assert row[0] == attempt
            if attempt < 5:
                delays.append(row[1] - h.clock.now())
                assert row[2] is None
                h.clock.advance(row[1] - h.clock.now())
            else:
                assert row[2] is not None
                assert len(row[3]) == 2000
        assert delays == [
            timedelta(seconds=10),
            timedelta(minutes=1),
            timedelta(minutes=5),
            timedelta(minutes=15),
        ]
        assert h.runs(usecase) == []

        with pytest.raises(NotAuthorised):
            h.service.list_dead_letters(person("sre"))
        (dead,) = h.service.list_dead_letters(COE)
        assert dead["event_type"] == "usecase.submitted"

        fault.failing.clear()
        h.service.requeue(COE, dead["event_id"])
        with pytest.raises(NotDeadLettered):
            h.service.requeue(COE, dead["event_id"])
        h.drain()
        assert [r.terminal_id for r in h.runs(usecase)] == ["T0"]
        action = h.sql("SELECT action, actor FROM events.dead_letter_action")[0]
        assert tuple(action) == ("requeue", "adlc_coe-person")


def test_retry_delays_are_time_scaled(orch_template: PlatformDatabase) -> None:
    with harness(orch_template, fault=Fault(), time_scale=0.01) as h:
        h.service.submit_usecase(person("business_owner"), "case", "x" * 250)
        h.drain()
        row = h.sql("SELECT next_attempt_at FROM events.outbox_event")[0]
        assert row[0] - h.clock.now() == timedelta(seconds=0.1)
