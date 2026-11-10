"""T047: timers from the pinned timeline, scaled, fired once (FR-021, research R-07)."""

from datetime import timedelta
from typing import Any

from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, harness
from tests.support.pg import PlatformDatabase


def _timers(h: Harness, run_id: str) -> list[tuple[Any, ...]]:
    return [
        tuple(r)
        for r in h.sql(
            "SELECT kind, due_at, fired_at, cancelled_at FROM run.timer WHERE run_id = :r ORDER BY timer_id",
            r=run_id,
        )
    ]


def test_durations_follow_the_tier(h: Harness) -> None:
    usecase, run_id = walk_to(h, "T1", tier="high")
    run = h.run(run_id)
    ((kind, due, fired, cancelled),) = _timers(h, run_id)
    assert kind == "escalate_after" and fired is None and cancelled is None
    assert due - run.opened_at == timedelta(days=10)


def test_time_scale(orch_template: PlatformDatabase) -> None:
    with harness(orch_template, time_scale=0.001) as h:
        usecase, run_id = walk_to(h, "T1")
        run = h.run(run_id)
        due = _timers(h, run_id)[0][1]
        assert due - run.opened_at == timedelta(days=10) * 0.001
        h.clock.advance(timedelta(minutes=15))
        h.drain()
        assert h.run(run_id).escalation_trigger == "timer"


def test_fires_once_after_downtime(h: Harness) -> None:
    usecase, run_id = walk_to(h, "T1")
    h.clock.advance(timedelta(days=100))
    assert h.orch.timers.drain() == 1
    assert h.orch.timers.drain() == 0
    assert _timers(h, run_id)[0][2] is not None


def test_closed_run_timers_are_cancelled_and_ignored(h: Harness) -> None:
    usecase, run_id = walk_to(h, "T1")
    h.pass_run(run_id)
    assert all(t[3] is not None for t in _timers(h, run_id))
    h.clock.advance(timedelta(days=30))
    h.drain()
    assert h.run(run_id).final_status == "pass"
