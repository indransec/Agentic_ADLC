"""Timer loop (research R-07; FR-018b, FR-021).

Due timers are taken one per transaction (``FOR UPDATE SKIP LOCKED``) and marked fired in the
same transaction as their effect, so an overdue timer fires once after downtime. A timer whose
run has moved on is ignored. ``review_due`` belongs to a closed continuous run: it asks the
router to open the next review run instead of signalling the closed run.
"""

from sqlalchemy import Engine

from adlc.orchestration import store
from adlc.orchestration.engine import ORCHESTRATOR_ID, PostgresTerminalRun
from adlc.orchestration.interfaces import Clock
from adlc.orchestration.router import PostgresRouter
from adlc.orchestration.states import ActorType, InvalidTransition, RunState, Signal, SignalKind


class TimerLoop:
    def __init__(
        self, engine: Engine, runs: PostgresTerminalRun, router: PostgresRouter, clock: Clock
    ) -> None:
        self.engine = engine
        self.runs = runs
        self.router = router
        self.clock = clock

    def fire_next(self) -> bool:
        now = self.clock.now()
        with self.engine.begin() as conn:
            due = store.take_due_timer(conn, now)
            if due is None:
                return False
            _, run_id, kind = due
            run = store.load_run(conn, run_id)
            if run is None:
                return True
            if kind == "review_due":
                if run.state == RunState.CLOSED:
                    self.router.open_review(conn, run_id)
                return True
            if run.state == RunState.CLOSED:
                return True  # a timer for a closed run is ignored
            savepoint = conn.begin_nested()
            try:
                self.runs.apply_in(
                    conn,
                    run_id,
                    Signal(
                        SignalKind.TIMER, ActorType.ORCHESTRATOR, ORCHESTRATOR_ID, {"kind": kind}
                    ),
                )
                savepoint.commit()
            except InvalidTransition:
                savepoint.rollback()  # the run moved on; the timer stays fired
        return True

    def drain(self) -> int:
        count = 0
        while self.fire_next():
            count += 1
        return count
