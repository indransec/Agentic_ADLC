"""The monitor evaluator (feature 012, FR-007, research R-02).

A terminal spec may declare ``monitors``: a signal, a threshold written as a policy expression,
and the operational event it raises (``<terminal>.event.<name>``). Every
``ADLC_MONITOR_INTERVAL`` the worker evaluates, for every active use case, the monitors of each
pinned spec that declares them, once that terminal has a run. Each evaluation is a policy
decision whose check id is the monitor id, on that terminal's latest run.

A threshold that becomes true raises its event once per breach episode (the monitor's previous
decision was not a breach), with the measured inputs. A threshold that cannot be evaluated, or
that rests on synthetic evidence, never fires. Nothing here names a terminal or a monitor.
"""

import logging
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import Engine, text

from adlc.orchestration import spec_view
from adlc.orchestration import store as run_store
from adlc.orchestration.interfaces import EvalContext, EvalResult, PolicyEngine
from adlc.orchestration.service import Actor, OrchestratorService, UnknownEvent
from adlc.orchestration.tracing import span
from adlc.spec_toolkit.registry import SpecRegistry

log = logging.getLogger(__name__)
EVENT = re.compile(r"^[A-Z][0-9]+\.event\.([a-z][a-z0-9_]*)$")
MONITOR_ACTOR = Actor.system("monitor")


@dataclass(frozen=True)
class Monitor:
    id: str
    signal: str
    threshold: str
    event: str  # the operational event name (``drift`` of ``<terminal>.event.drift``)


def declared_monitors(spec: Mapping[str, Any]) -> tuple[Monitor, ...]:
    found = []
    for m in spec_view.body(spec).get("monitors") or []:
        matched = EVENT.match(str(m.get("raises") or ""))
        if matched and m.get("threshold"):
            found.append(
                Monitor(
                    str(m["id"]), str(m.get("signal", "")), str(m["threshold"]), matched.group(1)
                )
            )
    return tuple(found)


def state_of(result: EvalResult) -> str:
    if result.passed:
        return "breach"
    return "clear" if result.value is False else "undecided"


def step(
    policy: PolicyEngine, monitor: Monitor, context: EvalContext, previous: str | None
) -> bool:
    """Evaluate one monitor; True when it starts a new breach episode (raise its event)."""
    result = policy.evaluate(monitor.threshold, context)
    return state_of(result) == "breach" and previous != "breach" and not result.synthetic


class MonitorEvaluator:
    def __init__(
        self,
        engine: Engine,
        registry: SpecRegistry,
        policy: PolicyEngine,
        service: OrchestratorService,
        interval: timedelta,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.engine, self.registry, self.policy, self.service = engine, registry, policy, service
        self.interval, self.clock = interval.total_seconds(), clock
        self.last: float | None = None

    def tick_if_due(self) -> int:
        now = self.clock()
        if self.last is not None and now - self.last < self.interval:
            return 0
        self.last = now
        return self.tick()

    def tick(self) -> int:
        """Evaluate every declared monitor once; returns the number of events raised."""
        raised = 0
        with self.engine.connect() as conn:
            usecases = [
                str(u)
                for u in conn.execute(
                    text("SELECT usecase_id FROM run.usecase WHERE status = 'active'")
                ).scalars()
            ]
            plans = []
            for usecase in usecases:
                for terminal, version in sorted(run_store.pins(conn, usecase).items()):
                    entry = self.registry.entry(terminal, version)
                    monitors = declared_monitors(entry.spec) if entry else ()
                    run_id = self._latest_run(conn, usecase, terminal) if monitors else None
                    if run_id:
                        plans.append((usecase, terminal, run_id, monitors))
        for usecase, terminal, run_id, monitors in plans:
            for monitor in monitors:
                with self.engine.connect() as conn:
                    previous = self._previous(conn, usecase, monitor.id)
                context = EvalContext(terminal, monitor.id, run_id, usecase)
                with span(
                    "policy", "monitor", usecase_id=usecase, run_id=run_id, terminal_id=terminal
                ) as current:
                    current.set_attribute("check_id", monitor.id)
                    fires = step(self.policy, monitor, context, previous)
                if fires and self._raise(usecase, terminal, run_id, monitor):
                    raised += 1
        return raised

    def _raise(self, usecase: str, terminal: str, run_id: str, monitor: Monitor) -> bool:
        payload = {
            "monitor_id": monitor.id,
            "signal": monitor.signal,
            "threshold": monitor.threshold,
            "measured": self._measured(run_id, monitor.id),
            "source_run_id": run_id,
        }
        try:
            self.service.raise_operational_event(MONITOR_ACTOR, usecase, monitor.event, payload)
        except UnknownEvent:  # the spec does not let this terminal raise it
            log.warning("monitor %s of %s may not raise %s", monitor.id, usecase, monitor.event)
            return False
        return True

    def _measured(self, run_id: str, monitor_id: str) -> Any:
        """The inputs of the decision that fired (the measured values the threshold read)."""
        with self.engine.connect() as conn:
            return conn.execute(
                text(
                    "SELECT inputs FROM run.policy_decision WHERE run_id = :r AND check_id = :c "
                    "ORDER BY policy_decision_id DESC LIMIT 1"
                ),
                {"r": run_id, "c": monitor_id},
            ).scalar()

    @staticmethod
    def _latest_run(conn: Any, usecase: str, terminal: str) -> str | None:
        found = conn.execute(
            text(
                "SELECT run_id FROM run.terminal_run WHERE usecase_id = :u AND terminal_id = :t "
                "ORDER BY run_number DESC LIMIT 1"
            ),
            {"u": usecase, "t": terminal},
        ).scalar()
        return None if found is None else str(found)

    @staticmethod
    def _previous(conn: Any, usecase: str, monitor_id: str) -> str | None:
        row = conn.execute(
            text(
                "SELECT passed, value FROM run.policy_decision WHERE usecase_id = :u "
                "AND check_id = :c ORDER BY policy_decision_id DESC LIMIT 1"
            ),
            {"u": usecase, "c": monitor_id},
        ).first()
        if row is None:
            return None
        return state_of(EvalResult(bool(row[0]), row[1]))
