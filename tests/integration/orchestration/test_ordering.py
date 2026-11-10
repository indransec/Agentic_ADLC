"""T063: per-use-case order; a retrying event blocks only its own use case (US6/AC6)."""

from datetime import timedelta

from adlc.orchestration import ids, store
from adlc.orchestration.store import EventRow
from tests.support.orchestration import Harness, harness
from tests.support.pg import PlatformDatabase


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


def test_failing_event_blocks_its_use_case_only(orch_template: PlatformDatabase) -> None:
    def fault(event: EventRow) -> None:
        if event.event_type == "T5.pass":
            raise RuntimeError("down")

    with harness(orch_template, fault=fault) as h:
        a = h.submit("a")
        b = h.submit("b")
        _event(h, a, "T5.pass")
        _event(h, a, "T6.pass")
        _event(h, b, "T6.pass")
        h.drain()
        assert [r.terminal_id for r in h.runs(a)] == ["T0"]  # T6.pass waits behind T5.pass
        assert [r.terminal_id for r in h.runs(b)] == ["T0", "T7"]
        for _ in range(5):
            h.clock.advance(timedelta(minutes=20))
            h.drain()
        assert [r.terminal_id for r in h.runs(a)] == ["T0", "T7"]  # unblocked by the dead letter
