"""T061: duplicate delivery never opens a second run (SC-005; US6/AC2, AC3)."""

import threading

from adlc.orchestration import ids, store
from adlc.orchestration.service import Actor
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, person


def test_redelivery_is_skipped(h: Harness) -> None:
    usecase, _ = walk_to(h, "T3")
    runs_before = [r.run_id for r in h.runs(usecase)]
    with h.owner.begin() as conn:  # make every event look undelivered again
        from sqlalchemy import text

        conn.execute(text("UPDATE events.outbox_event SET processed_at = NULL"))
    h.drain()
    assert [r.run_id for r in h.runs(usecase)] == runs_before


def test_two_workers_deliver_each_event_once(h: Harness) -> None:
    usecases = [h.service.submit_usecase(_owner(), f"case {n}", "x" * 250) for n in range(6)]
    barrier = threading.Barrier(2)

    def worker() -> None:
        barrier.wait()
        while h.orch.outbox.process_next():
            pass

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for usecase in usecases:
        assert [r.terminal_id for r in h.runs(usecase)] == ["T0"]


def test_event_for_an_active_run_is_a_signal(h: Harness) -> None:
    usecase, t1 = walk_to(h, "T1")
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
    assert [r.run_id for r in h.runs(usecase) if r.terminal_id == "T1"] == [t1]
    assert h.run(t1).received_events[-1]["event_type"] == "T0.exception"


def _owner() -> Actor:
    return person("business_owner")
