"""Outbox delivery (research R-08; contracts/events.md; FR-028, FR-029).

One event per transaction: the oldest due event of a use case with no older pending event is
locked (``FOR UPDATE SKIP LOCKED``), routed, and marked processed together with its
``processed_event`` row, so a crash never half-delivers and a repeat is skipped. A failure is
rolled back to a savepoint and recorded on the event: retried after 10 s, 1 min, 5 min, 15 min
(time-scaled), and dead-lettered on the fifth failure.
"""

import logging
from datetime import timedelta

from sqlalchemy import Engine

from adlc.orchestration import durations, store
from adlc.orchestration.interfaces import Clock
from adlc.orchestration.router import Router

log = logging.getLogger(__name__)

RETRY_DELAYS = (
    timedelta(seconds=10),
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
)
MAX_ATTEMPTS = len(RETRY_DELAYS) + 1


def next_delay(attempts: int) -> timedelta | None:
    """Delay before the next try after ``attempts`` failures; ``None`` means dead-letter."""
    if attempts >= MAX_ATTEMPTS:
        return None
    return RETRY_DELAYS[attempts - 1]


class OutboxProcessor:
    def __init__(
        self, engine: Engine, router: Router, clock: Clock, time_scale: float = 1.0
    ) -> None:
        self.engine = engine
        self.router = router
        self.clock = clock
        self.time_scale = time_scale

    def process_next(self) -> bool:
        """Deliver one due event; ``False`` when none is due."""
        now = self.clock.now()
        with self.engine.begin() as conn:
            event = store.take_next_event(conn, now)
            if event is None:
                return False
            if store.already_processed(conn, event.event_id):
                store.mark_processed(conn, event.event_id, now)
                return True
            savepoint = conn.begin_nested()
            try:
                self.router.handle(conn, event)
                store.mark_processed(conn, event.event_id, now)
                savepoint.commit()
            except Exception as exc:  # any routing failure is retried, never lost
                savepoint.rollback()
                attempts = event.attempts + 1
                delay = next_delay(attempts)
                next_at = None if delay is None else now + durations.scaled(delay, self.time_scale)
                store.record_failure(
                    conn, event.event_id, attempts, f"{type(exc).__name__}: {exc}", next_at, now
                )
                log.warning(
                    "event %s (%s) failed, attempt %s%s",
                    event.event_id,
                    event.event_type,
                    attempts,
                    "; dead-lettered" if next_at is None else "",
                )
        return True

    def drain(self) -> int:
        count = 0
        while self.process_next():
            count += 1
        return count
