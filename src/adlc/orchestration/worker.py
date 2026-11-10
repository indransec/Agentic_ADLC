"""The orchestrator process loop (research R-11): deliver events, advance automatic runs, fire
timers, beat the heartbeat. ``drain`` repeats until nothing is left, which makes tests and
scenarios deterministic; ``run_forever`` waits on ``LISTEN adlc_outbox`` between rounds.
"""

import logging
import select
import socket
import threading
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import Engine

from adlc.orchestration import store
from adlc.orchestration.engine import EngineConfig, PostgresTerminalRun
from adlc.orchestration.interfaces import AgentRunner, Clock, PolicyEngine, Reviewer
from adlc.orchestration.outbox import OutboxProcessor
from adlc.orchestration.router import FaultHook, PostgresRouter
from adlc.orchestration.service import OrchestratorService
from adlc.orchestration.timers import TimerLoop
from adlc.spec_toolkit.registry import SpecRegistry

log = logging.getLogger(__name__)
CHANNEL = "adlc_outbox"


@dataclass
class Orchestrator:
    runs: PostgresTerminalRun
    router: PostgresRouter
    outbox: OutboxProcessor
    timers: TimerLoop
    service: OrchestratorService
    worker_id: str

    def drain(self, max_rounds: int = 10_000) -> int:
        """Deliver, advance and fire until nothing changes; returns the number of steps."""
        total = 0
        for _ in range(max_rounds):
            steps = self.outbox.drain()
            while self.runs.advance():
                steps += 1
            steps += self.timers.drain()
            total += steps
            if steps == 0:
                return total
        raise RuntimeError("orchestrator did not settle")

    def run_once(self) -> int:
        steps = self.drain()
        with self.runs.engine.begin() as conn:
            store.beat(conn, self.worker_id, self.runs.clock.now())
        return steps

    def run_forever(self, poll_interval: timedelta, stop: threading.Event) -> None:
        raw = self.runs.engine.raw_connection()
        try:
            dbapi = raw.driver_connection
            if dbapi is None:
                raise RuntimeError("no database connection for LISTEN")
            dbapi.autocommit = True
            dbapi.execute(f"LISTEN {CHANNEL}")
            while not stop.is_set():
                try:
                    self.run_once()
                except Exception:  # keep the loop alive; the failing step is retried
                    log.exception("orchestrator round failed")
                ready, _, _ = select.select([dbapi.fileno()], [], [], poll_interval.total_seconds())
                if ready:
                    for _ in dbapi.notifies(timeout=0):
                        pass
        finally:
            raw.close()


def build_orchestrator(
    engine: Engine,
    registry: SpecRegistry,
    policy: PolicyEngine,
    agent: AgentRunner,
    reviewer: Reviewer,
    clock: Clock,
    *,
    deadletter_role: str,
    config: EngineConfig | None = None,
    fault: FaultHook | None = None,
    worker_id: str | None = None,
) -> Orchestrator:
    config = config or EngineConfig()
    runs = PostgresTerminalRun(engine, registry, policy, agent, reviewer, clock, config)
    router = PostgresRouter(runs, fault)
    return Orchestrator(
        runs=runs,
        router=router,
        outbox=OutboxProcessor(engine, router, clock, config.time_scale),
        timers=TimerLoop(engine, runs, router, clock),
        service=OrchestratorService(runs, deadletter_role),
        worker_id=worker_id or socket.gethostname(),
    )
