"""The orchestrator process loop (research R-11): deliver events, advance automatic runs, fire
timers, beat the heartbeat. ``drain`` repeats until nothing is left, which makes tests and
scenarios deterministic; ``run_forever`` waits ``ADLC_POLL_INTERVAL`` between rounds.
"""

import logging
import socket
import threading
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import Engine

from adlc.orchestration import store
from adlc.orchestration.engine import EngineConfig, SqlTerminalRun
from adlc.orchestration.interfaces import AgentRunner, Clock, PolicyEngine, Reviewer
from adlc.orchestration.monitors import MonitorEvaluator
from adlc.orchestration.outbox import OutboxProcessor
from adlc.orchestration.router import FaultHook, SqlRouter
from adlc.orchestration.service import OrchestratorService
from adlc.orchestration.timers import TimerLoop
from adlc.spec_toolkit.registry import SpecRegistry

log = logging.getLogger(__name__)


@dataclass
class Orchestrator:
    runs: SqlTerminalRun
    router: SqlRouter
    outbox: OutboxProcessor
    timers: TimerLoop
    service: OrchestratorService
    worker_id: str
    monitors: MonitorEvaluator | None = None  # 012: declared monitors, every monitor interval

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
        if self.monitors is not None:
            try:
                self.monitors.tick_if_due()  # an event it raises is delivered by the drain
            except Exception:  # a monitor round must never stop the worker
                log.exception("monitor round failed")
        steps = self.drain()
        with self.runs.engine.begin() as conn:
            store.beat(conn, self.worker_id, self.runs.clock.now())
        return steps

    def run_forever(self, poll_interval: timedelta, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                self.run_once()
            except Exception:  # keep the loop alive; the failing step is retried
                log.exception("orchestrator round failed")
            stop.wait(poll_interval.total_seconds())


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
    runs = SqlTerminalRun(engine, registry, policy, agent, reviewer, clock, config)
    router = SqlRouter(runs, fault)
    return Orchestrator(
        runs=runs,
        router=router,
        outbox=OutboxProcessor(engine, router, clock, config.time_scale),
        timers=TimerLoop(engine, runs, router, clock),
        service=OrchestratorService(runs, deadletter_role),
        worker_id=worker_id or socket.gethostname(),
    )
