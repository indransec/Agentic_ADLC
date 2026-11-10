"""Event router (research R-05, R-06; FR-015 to FR-018).

``handle`` runs inside the delivery transaction. For each terminal whose **pinned** spec
subscribes to the event (or that the event names explicitly: a self-route or a resolver
destination), it signals the active run or opens a new one. Operational events also follow the
raising terminal's event routes: immediate actions are recorded, and a ``then`` event is written
when its condition holds.
"""

from collections.abc import Callable
from typing import Any, Protocol

from sqlalchemy import Connection

from adlc.orchestration import ids, routing, store
from adlc.orchestration.engine import (
    ORCHESTRATOR_ID,
    PostgresTerminalRun,
    Trigger,
    json_dict,
    json_safe,
)
from adlc.orchestration.interfaces import EvalContext
from adlc.orchestration.states import ActorType, Signal, SignalKind
from adlc.orchestration.store import EventRow
from adlc.orchestration.tracing import span

FaultHook = Callable[[EventRow], None]

_CONTEXT_KEYS = (
    "comment",
    "root_cause",
    "decision_fields",
    "ledger_key",
    "status",
    "emits",
    "reentry_terminal",
)


class Router(Protocol):
    def handle(self, conn: Connection, event: EventRow) -> None: ...


class PostgresRouter:
    def __init__(self, runs: PostgresTerminalRun, fault: FaultHook | None = None) -> None:
        self.runs = runs
        self.fault = fault  # test hook: raise for chosen events (research R-08)

    def handle(self, conn: Connection, event: EventRow) -> None:
        if self.fault is not None:
            self.fault(event)
        if event.usecase_id is None:
            return
        usecase = store.load_usecase(conn, event.usecase_id)
        if usecase is None or usecase.status != "active":
            return  # recorded (processed) and ignored: the lifecycle has ended
        pinned = {
            tid: self.runs.entry(tid, version).spec
            for tid, version in store.pins(conn, event.usecase_id).items()
        }
        self._event_route(conn, event)
        targets = list(routing.subscribers(pinned, event.event_type))
        named = event.payload.get("target_terminal")
        if isinstance(named, str) and named in pinned and named not in targets:
            targets.append(named)  # self-route or resolver destination (FR-015 exceptions)
        trigger = Trigger(event.event_type, event.event_id, self._trigger_context(event))
        for terminal_id in targets:
            with span("router", "route", usecase_id=event.usecase_id, terminal_id=terminal_id):
                active = store.active_run(conn, event.usecase_id, terminal_id)
                if active is None:
                    self.runs.open_in(conn, event.usecase_id, terminal_id, trigger)
                else:
                    self.runs.apply_in(
                        conn,
                        active,
                        Signal(
                            SignalKind.EVENT_RECEIVED,
                            ActorType.ORCHESTRATOR,
                            ORCHESTRATOR_ID,
                            {"event_type": event.event_type, "event_id": str(event.event_id)},
                        ),
                    )

    def open_review(self, conn: Connection, closed_run_id: str) -> str | None:
        """Open the next review run of a continuous terminal (``review_due`` timer, FR-018b)."""
        run = store.load_run(conn, closed_run_id)
        if run is None:
            return None
        usecase = store.load_usecase(conn, run.usecase_id)
        if usecase is None or usecase.status != "active":
            return None
        if store.active_run(conn, run.usecase_id, run.terminal_id) is not None:
            return None
        cause = store.event_caused_by(conn, closed_run_id)
        trigger = Trigger(
            cause[1] if cause else run.trigger_event_type,
            cause[0] if cause else None,
            {"causing_run_id": closed_run_id, "review": "scheduled"},
        )
        return self.runs.open_in(conn, run.usecase_id, run.terminal_id, trigger)

    @staticmethod
    def _trigger_context(event: EventRow) -> dict[str, Any]:
        context: dict[str, Any] = {
            key: event.payload[key] for key in _CONTEXT_KEYS if event.payload.get(key) is not None
        }
        context["causing_run_id"] = event.causation_run_id
        if ".event." in event.event_type:
            context["operational_event"] = event.payload
        return json_dict(context)

    def _event_route(self, conn: Connection, event: EventRow) -> None:
        source = routing.event_source(event.event_type)
        if event.usecase_id is None:
            return
        version = store.pins(conn, event.usecase_id).get(source)
        if version is None:
            return
        route = self.runs.registry.event_route(source, event.event_type, version)
        if route is None:
            return
        now = self.runs.clock.now()
        source_run = store.active_run(conn, event.usecase_id, source)
        follow_on = None
        if route.then_destination:
            condition = route.condition or "true"
            check = self.runs.policy.evaluate(
                condition,
                EvalContext(
                    source,
                    f"then_when:{event.event_type}",
                    source_run,
                    event.usecase_id,
                    {"trigger": event.payload},
                ),
            )
            if check.passed:
                follow_on = route.then_destination
                store.insert_event(
                    conn,
                    event_id=ids.uuid7(),
                    event_type=follow_on,
                    usecase_id=event.usecase_id,
                    correlation_id=event.correlation_id,
                    causation_run_id=event.causation_run_id or source_run,
                    payload=json_safe(
                        {"cause_event_id": str(event.event_id), "cause_event": event.event_type}
                    ),
                    now=now,
                )
        if source_run is not None:
            store.insert_activity(
                conn,
                source_run,
                "route",
                "orchestrator",
                ORCHESTRATOR_ID,
                now,
                now,
                "event_route",
                {
                    "event_type": event.event_type,
                    "destination": route.destination,
                    "destination_kind": route.kind,
                    "immediate": list(route.immediate),
                    "notify": list(route.notify),
                    "follow_on": follow_on,
                },
            )
