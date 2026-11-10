"""T027: delivery in order, processed with its idempotency row; subscriptions only (FR-015, FR-028)."""

from adlc.orchestration import ids, store
from tests.support.orchestration import Harness


def _event(h: Harness, usecase: str, event_type: str) -> None:
    with h.app.begin() as conn:
        store.insert_event(
            conn,
            event_id=ids.uuid7(),
            event_type=event_type,
            usecase_id=usecase,
            correlation_id=ids.correlation_id(usecase),
            causation_run_id=None,
            payload={},
            now=h.clock.now(),
        )


def test_processed_with_idempotency_row(h: Harness) -> None:
    h.submit()
    rows = h.sql(
        "SELECT e.event_type, e.processed_at IS NOT NULL, p.event_id IS NOT NULL "
        "FROM events.outbox_event e LEFT JOIN events.processed_event p USING (event_id)"
    )
    assert [tuple(r) for r in rows] == [("usecase.submitted", True, True)]


def test_non_subscriber_does_not_open(h: Harness) -> None:
    usecase = h.submit()
    _event(h, usecase, "T5.pass")  # T6 subscribes to T5.pass ...
    _event(h, usecase, "T3.escalate")  # ... nobody subscribes to an escalation notice
    h.drain()
    terminals = sorted(r.terminal_id for r in h.runs(usecase))
    assert terminals == ["T0", "T6"]


def test_order_per_usecase(h: Harness) -> None:
    usecase = h.submit()
    for event_type in ("T5.pass", "T6.pass", "T7.pass"):
        _event(h, usecase, event_type)
    h.drain()
    opened = [r.terminal_id for r in h.runs(usecase)]
    assert opened == ["T0", "T6", "T7", "T8"]
    processed = h.sql(
        "SELECT event_type FROM events.outbox_event WHERE usecase_id = :u ORDER BY processed_at, created_at",
        u=usecase,
    )
    assert [r[0] for r in processed][:4] == ["usecase.submitted", "T5.pass", "T6.pass", "T7.pass"]
