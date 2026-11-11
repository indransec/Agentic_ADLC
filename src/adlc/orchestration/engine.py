"""PostgreSQL terminal-run engine (research R-01, R-02; contracts/state-machine.md).

* ``apply`` changes a run only through :func:`states.transition`, in one transaction that locks
  the run row and writes the state, its transition and activity rows, and every effect. A
  closing signal also writes the sign-offs, the ledger record and the outcome event (FR-026).
* ``advance`` runs one automatic step: it leases a run, calls the policy engine, agent or
  reviewer outside any transaction, and applies the result only if the run has not moved on
  meanwhile (``version`` check); otherwise the result is recorded as stale (FR-030b).
"""

import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, Engine

from adlc.ledger import artifacts as versions
from adlc.ledger import profile as profiles
from adlc.ledger import store as ledger_store
from adlc.ledger.artifacts import Change, NewAttachment, Producer
from adlc.ledger.binding import resolve_bound_to
from adlc.ledger.content import build_v2
from adlc.ledger.storage import FileRef, put_structured
from adlc.ledger.storage import versions_exist as store_versions_exist
from adlc.ledger.views import checklist_rows
from adlc.orchestration import durations, ids, routing, spec_view, store
from adlc.orchestration.interfaces import (
    AgentRunner,
    Artifacts,
    AttemptFailed,
    BudgetExceeded,
    BuildContext,
    Clarification,
    Clock,
    EvalContext,
    ModelUnavailable,
    PolicyEngine,
    Recommendation,
    ReviewContext,
    Reviewer,
)
from adlc.orchestration.ledger import make_record
from adlc.orchestration.states import (
    ActorType,
    CancelAllTimers,
    CancelTimer,
    ClearApprovals,
    CloseRun,
    DecideWaiver,
    Effect,
    Escalate,
    IncrementAutoRetry,
    InvalidTransition,
    ProposeWaiver,
    RecordClarification,
    RecordEvent,
    RecordSignOff,
    RunState,
    SetControlsPending,
    SetReturnState,
    Signal,
    SignalKind,
    StartTimer,
    StoreArtifacts,
    StoreControls,
    StoreRecommendation,
    TransitionContext,
    WithdrawWaiver,
    transition,
)
from adlc.orchestration.store import RunRow
from adlc.orchestration.tracing import span
from adlc.spec_toolkit.registry import RegistryEntry, SpecRegistry, TimelinePolicy

DEFAULT_TIER = "medium"
WITHDRAWN_BY = "system:artifact-edited"
WITHDRAWN_COMMENT = "withdrawn: artifact edited"
ORCHESTRATOR_ID = "orchestrator"

_STEP_BY_SIGNAL = {
    SignalKind.PREREQUISITES_RESULT: "prerequisites",
    SignalKind.EVENT_RECEIVED: "route",
    SignalKind.AGENT_RESULT: "build",
    SignalKind.CONTROLS_RESULT: "controls",
    SignalKind.REVIEW_RESULT: "review",
    SignalKind.CLARIFICATION_ANSWERED: "clarification",
    SignalKind.DECIDE: "sign_off",
    SignalKind.WAIVER_DECISION: "waiver",
    SignalKind.ESCALATION_COMPLETED: "escalation",
    SignalKind.TIMER: "timer",
    SignalKind.OPEN_ESCALATED: "escalation",
    SignalKind.LIFECYCLE_ENDED: "close",
    SignalKind.ARTIFACT_EDITED: "sign_off",
    SignalKind.CONTROLS_RECHECKED: "controls",
}
_STEP_BY_STATE = {
    RunState.OPENED: "prerequisites",
    RunState.BUILDING: "build",
    RunState.CHECKING: "controls",
    RunState.REVIEWING: "review",
}


class StaleRun(Exception):
    """The run changed after the caller read it (optimistic version check)."""


class UnknownRun(Exception):
    pass


@dataclass(frozen=True)
class Trigger:
    event_type: str
    event_id: UUID | None = None
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineConfig:
    time_scale: float = 1.0
    lease: timedelta = timedelta(minutes=5)
    model_outage_limit: timedelta = timedelta(minutes=30)  # 006 FR-006
    outage_backoff: timedelta = timedelta(seconds=30)  # doubling
    outage_backoff_max: timedelta = timedelta(minutes=5)


def json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def json_dict(value: Mapping[str, Any]) -> dict[str, Any]:
    return dict(json_safe(value))


class PostgresTerminalRun:
    def __init__(
        self,
        engine: Engine,
        registry: SpecRegistry,
        policy: PolicyEngine,
        agent: AgentRunner,
        reviewer: Reviewer,
        clock: Clock,
        config: EngineConfig | None = None,
    ) -> None:
        self.engine = engine
        self.registry = registry
        self.policy = policy
        self.agent = agent
        self.reviewer = reviewer
        self.clock = clock
        self.config = config or EngineConfig()

    # -------------------------------------------------------------- spec lookups

    def entry(self, terminal_id: str, version: str) -> RegistryEntry:
        entry = self.registry.entry(terminal_id, version)
        if entry is None:
            raise UnknownRun(f"no registered spec {terminal_id} {version}")
        return entry

    def tier(self, conn: Connection, usecase_id: str) -> str:
        usecase = store.load_usecase(conn, usecase_id)
        return (usecase.risk_tier if usecase else None) or DEFAULT_TIER

    def timeline(self, terminal_id: str, tier: str, version: str) -> TimelinePolicy | None:
        return self.registry.timeline(terminal_id, tier, version)

    def scaled(self, value: timedelta) -> timedelta:
        return durations.scaled(value, self.config.time_scale)

    def destination_kind(self, destination: str) -> str | None:
        catalogue = self.registry.catalogue("route_destinations")
        for item in (catalogue.content if catalogue else {}).get("route_destinations", []):
            if item.get("id") == destination:
                return str(item.get("kind"))
        return None

    # -------------------------------------------------------------- open

    def open_in(self, conn: Connection, usecase_id: str, terminal_id: str, trigger: Trigger) -> str:
        now = self.clock.now()
        version = store.pins(conn, usecase_id)[terminal_id]
        tier = self.tier(conn, usecase_id)
        timeline = self.timeline(terminal_id, tier, version)
        history = store.run_history(conn, usecase_id, terminal_id)
        number = len(history) + 1
        run_id = ids.run_id(usecase_id, terminal_id, number)
        rework = routing.rework_count([t for _, t in history], trigger.event_type)
        expected = durations.parse_optional(timeline.expected_duration if timeline else None)
        store.insert_run(
            conn,
            run_id=run_id,
            usecase_id=usecase_id,
            terminal_id=terminal_id,
            run_number=number,
            spec_version=version,
            mode=routing.run_mode(trigger.event_type),
            trigger_event_id=trigger.event_id,
            trigger_event_type=trigger.event_type,
            trigger_context=json_safe(trigger.context),
            rework_count=rework,
            now=now,
            due_at=None if expected is None else now + self.scaled(expected),
            profile_version=profiles.current_version(conn, usecase_id)[0],
        )
        store.insert_transition(
            conn,
            run_id,
            None,
            RunState.OPENED,
            "open",
            "orchestrator",
            ORCHESTRATOR_ID,
            trigger.event_type,
            now,
        )
        store.insert_activity(
            conn,
            run_id,
            "route",
            "orchestrator",
            ORCHESTRATOR_ID,
            now,
            now,
            "opened",
            {"trigger": trigger.event_type, "rework_count": rework},
        )
        escalate_after = durations.parse_optional(timeline.escalate_after if timeline else None)
        if escalate_after is not None:
            store.insert_timer(conn, run_id, "escalate_after", now + self.scaled(escalate_after))
        if timeline is not None and routing.over_rework_limit(rework, timeline.max_rework_cycles):
            self.apply_in(
                conn,
                run_id,
                Signal(
                    SignalKind.OPEN_ESCALATED,
                    ActorType.ORCHESTRATOR,
                    ORCHESTRATOR_ID,
                    {"trigger": "rework_limit"},
                ),
            )
        return run_id

    # -------------------------------------------------------------- apply

    def apply(self, run_id: str, signal: Signal, expected_version: int | None = None) -> RunRow:
        with self.engine.begin() as conn:
            return self.apply_in(conn, run_id, signal, expected_version)

    def context(self, conn: Connection, run: RunRow, *, sign_off: bool = True) -> TransitionContext:
        """``sign_off=False`` skips the approver conditions (only decisions need them)."""
        entry = self.entry(run.terminal_id, run.spec_version)
        tier = self.tier(conn, run.usecase_id)
        timeline = self.timeline(run.terminal_id, tier, run.spec_version)
        rule = spec_view.sign_off_rule(entry.spec, tier, run.mode)
        with span(
            "policy",
            "sign_off_rule",
            run_id=run.run_id,
            usecase_id=run.usecase_id,
            terminal_id=run.terminal_id,
        ):
            required_plus = frozenset(
                p.role
                for p in (rule.plus if sign_off else ())
                if self.policy.evaluate(
                    p.condition,
                    EvalContext(run.terminal_id, f"plus:{p.role}", run.run_id, run.usecase_id),
                ).passed
            )
        cutoff = run.approvals_after_sign_off_id or 0
        approvals = tuple(
            (str(s["person"]), str(s["role"]))
            for s in store.sign_offs(conn, run.run_id)
            # 005: approvals given before the last artifact edit no longer count (FR-010)
            if s["decision"] == "pass" and int(s["sign_off_id"]) > cutoff
        )
        return TransitionContext(
            max_clarification_rounds=timeline.max_clarification_rounds if timeline else 2,
            max_auto_retries=(timeline.max_auto_retries if timeline else None) or 3,
            clarification_rounds=run.clarification_rounds,
            auto_retries=run.auto_retries,
            return_state=run.return_state,
            pending_waiver=run.pending_waiver_id is not None,
            min_approvers=rule.min_approvers,
            rule_roles=rule.roles,
            required_plus_roles=required_plus,
            approvals=approvals,
            controls_pending=run.controls_pending,
        )

    def apply_in(
        self,
        conn: Connection,
        run_id: str,
        signal: Signal,
        expected_version: int | None = None,
        started_at: datetime | None = None,
    ) -> RunRow:
        now = self.clock.now()
        run = store.load_run(conn, run_id, lock=True)
        if run is None:
            raise UnknownRun(run_id)
        if expected_version is not None and run.version != expected_version:
            raise StaleRun(f"{run_id} is at version {run.version}, not {expected_version}")
        context = self.context(conn, run, sign_off=signal.kind == SignalKind.DECIDE)
        outcome = transition(run.state, signal, context)
        new = replace(run, state=outcome.next_state)
        for effect in outcome.effects:
            new = self._effect(conn, run, new, signal, effect, now)
        if signal.kind in (SignalKind.AGENT_RESULT, SignalKind.REVIEW_RESULT):
            new = replace(new, model_unavailable_since=None)  # 006: any step result ends it
        store.save_run(conn, new, now)
        store.insert_transition(
            conn,
            run_id,
            run.state,
            new.state,
            signal.kind.value,
            signal.actor_type.value,
            signal.actor_id,
            _reason(signal),
            now,
        )
        step = _STEP_BY_SIGNAL.get(signal.kind) or _STEP_BY_STATE.get(run.state, "route")
        store.insert_activity(
            conn,
            run_id,
            step,
            signal.actor_type.value,
            signal.actor_id,
            started_at or now,
            now,
            new.state.value,
            _detail(signal),
        )
        return replace(new, version=new.version + 1)

    def _effect(
        self,
        conn: Connection,
        before: RunRow,
        run: RunRow,
        signal: Signal,
        effect: Effect,
        now: datetime,
    ) -> RunRow:
        p = signal.payload
        match effect:
            case StartTimer(kind=kind):
                timeline = self.timeline(
                    run.terminal_id, self.tier(conn, run.usecase_id), run.spec_version
                )
                after = durations.parse_optional(timeline.clarification_sla if timeline else None)
                if after is not None:
                    store.insert_timer(conn, run.run_id, kind, now + self.scaled(after))
            case CancelTimer(kind=kind):
                store.cancel_timers(conn, run.run_id, now, kind)
            case CancelAllTimers():
                store.cancel_timers(conn, run.run_id, now)
            case Escalate(trigger=trigger):
                return self._escalate(conn, run, trigger, now)
            case RecordSignOff(decision=decision):
                store.insert_sign_off(
                    conn, run.run_id, str(p.get("role", "")), signal.actor_id, decision, p, now
                )
            case ProposeWaiver():
                return self._propose_waiver(conn, run, signal, now)
            case DecideWaiver(approve=approve):
                if run.pending_waiver_id is None:
                    raise InvalidTransition("no pending waiver")
                store.decide_waiver(
                    conn, run.pending_waiver_id, approve, signal.actor_id, p.get("comment"), now
                )
                if not approve:
                    return replace(run, pending_waiver_id=None)
            case RecordClarification(asked_by=asked_by):
                return self._clarification(conn, run, asked_by, p.get("clarification") or {}, now)
            case SetReturnState(state=state):
                return replace(run, return_state=state)
            case IncrementAutoRetry():
                return replace(run, auto_retries=run.auto_retries + 1)
            case StoreArtifacts():
                return self._store_artifacts(conn, run, signal)
            case StoreControls():
                return replace(run, control_results=list(p.get("results") or []))
            case StoreRecommendation():
                recommendation = dict(p.get("recommendation") or {})
                ledger_store.insert_checklist_results(
                    conn, run.run_id, run.auto_retries + 1, checklist_rows(recommendation)
                )
                return replace(run, recommendation=recommendation)
            case SetControlsPending(pending=pending):
                return replace(run, controls_pending=pending)
            case ClearApprovals():
                return replace(
                    run, approvals_after_sign_off_id=store.max_sign_off_id(conn, run.run_id)
                )
            case WithdrawWaiver():
                if run.pending_waiver_id is not None:
                    store.decide_waiver(
                        conn, run.pending_waiver_id, False, WITHDRAWN_BY, WITHDRAWN_COMMENT, now
                    )
                return replace(run, pending_waiver_id=None)
            case RecordEvent():
                received = {"event_type": p.get("event_type"), "event_id": str(p.get("event_id"))}
                return replace(run, received_events=[*run.received_events, received])
            case CloseRun(status=status):
                return self._close(conn, run, signal, status, now)
        return run

    # -------------------------------------------------------------- effect helpers

    def _escalate(self, conn: Connection, run: RunRow, trigger: str, now: datetime) -> RunRow:
        store.cancel_timers(conn, run.run_id, now)
        route = self.registry.outcome_route(run.terminal_id, "escalate", version=run.spec_version)
        destination = route.destination if route else None
        store.insert_event(
            conn,
            event_id=ids.uuid7(),
            event_type=routing.escalate_event_type(run.terminal_id),
            usecase_id=run.usecase_id,
            correlation_id=ids.correlation_id(run.usecase_id),
            causation_run_id=run.run_id,
            payload={
                "run_id": run.run_id,
                "trigger": trigger,
                "destination": destination,
                "notify": list(route.notify) if route else [],
            },
            now=now,
        )
        return replace(run, escalation_trigger=trigger, escalation_destination=destination)

    def _propose_waiver(
        self, conn: Connection, run: RunRow, signal: Signal, now: datetime
    ) -> RunRow:
        fields = dict(signal.payload.get("fields") or {})
        entry = self.entry(run.terminal_id, run.spec_version)
        waiver = ids.waiver_id(store.next_waiver_number(conn))
        recheck = spec_view.outcome(entry.spec, "exception").get("recheck_at") or []
        store.insert_waiver(
            conn,
            waiver_id=waiver,
            run_id=run.run_id,
            owner=fields.get("waiver_owner"),
            compensating_control=fields.get("compensating_control"),
            expiry=None if fields.get("expiry") is None else str(fields["expiry"]),
            recheck_at=[str(r) for r in recheck],
            requires=fields,
            proposed_by=signal.actor_id,
            now=now,
        )
        return replace(run, pending_waiver_id=waiver)

    def _clarification(
        self,
        conn: Connection,
        run: RunRow,
        asked_by: str,
        request: Mapping[str, Any],
        now: datetime,
    ) -> RunRow:
        number = run.clarification_rounds + 1
        entry = self.entry(run.terminal_id, run.spec_version)
        addressed = request.get("addressed_role") or spec_view.default_addressee(entry.spec) or ""
        store.insert_clarification(
            conn,
            ids.clarification_id(run.run_id, number),
            run.run_id,
            asked_by,
            str(addressed),
            [str(q) for q in request.get("questions") or []],
            [str(s) for s in request.get("looked_in") or []],
            now,
        )
        return replace(run, clarification_rounds=number)

    def _close(
        self, conn: Connection, run: RunRow, signal: Signal, status: str, now: datetime
    ) -> RunRow:
        closed = replace(run, final_status=status, closed_at=now)
        entry = self.entry(run.terminal_id, run.spec_version)
        store.cancel_timers(conn, run.run_id, now)
        p = signal.payload
        if signal.kind == SignalKind.LIFECYCLE_ENDED:
            self._write_ledger(conn, closed, entry, {}, now)  # (key, emitted) not needed here
            return closed

        fields = dict(p.get("fields") or {})
        root_cause = p.get("root_cause") if status == "rework" else None
        reentry: str | None = None
        open_terminal: str | None = None
        ends_lifecycle = status == "terminate"
        continues = False
        emitted: dict[str, Any] = {}

        route = self.registry.outcome_route(run.terminal_id, status, root_cause, run.spec_version)
        if route is not None and status in ("pass", "exception"):
            alternative = fields.get("alternative")
            if alternative:
                ends_lifecycle = self.destination_kind(str(alternative)) == "terminating"
            elif route.kind == "template":
                reentry = routing.resolve_template(
                    route.destination, run.terminal_id, run.artifacts
                )
            else:
                kind = (
                    route.kind
                    if route.kind != "special"
                    else self.destination_kind(route.destination)
                )
                continues = kind == "continue"
                ends_lifecycle = kind == "terminating"
        if status == "pass":
            attributes = {"usecase_id": run.usecase_id}
            emitted = routing.emitted_values(entry.spec, run.artifacts, attributes, fields).values
        if status == "rework" and route is not None:
            if route.destination == run.terminal_id:
                open_terminal = run.terminal_id  # self-route (002 rule V-17)
            elif self.destination_kind(route.destination) == "terminal_resolver":
                open_terminal = str(p.get("target_terminal"))

        bodies = self._notified_bodies(conn, closed, entry, now) if status == "pass" else []
        record, emitted = self._write_ledger(conn, closed, entry, emitted, now)
        profiles.on_close(conn, run.usecase_id, run.run_id, status, emitted)
        event_type = routing.outcome_event_type(run.terminal_id, status, root_cause, reentry)
        store.insert_event(
            conn,
            event_id=ids.uuid7(),
            event_type=event_type,
            usecase_id=run.usecase_id,
            correlation_id=ids.correlation_id(run.usecase_id),
            causation_run_id=run.run_id,
            payload=json_safe(
                {
                    "ledger_key": record,
                    "run_id": run.run_id,
                    "status": status,
                    "root_cause": root_cause,
                    "comment": p.get("comment"),
                    "decision_fields": fields,
                    "target_terminal": open_terminal,
                    "reentry_terminal": reentry,
                    "waiver_id": run.pending_waiver_id,
                    "emits": emitted,
                    "notify": list(route.notify) if route else [],
                    "notify_bodies": bodies,
                }
            ),
            now=now,
        )
        tier = emitted.get("risk_tier")
        if isinstance(tier, str):
            store.set_usecase_tier(conn, run.usecase_id, tier)
        if continues:
            self._schedule_review(conn, closed, entry, now)
        if ends_lifecycle:
            self._end_lifecycle(conn, closed, signal, event_type, status, now)
        return closed

    def _notified_bodies(
        self, conn: Connection, run: RunRow, entry: RegistryEntry, now: datetime
    ) -> list[str]:
        """FR-009c: board and external approvals are recorded as notifications, not gates."""
        rule = spec_view.sign_off_rule(entry.spec, self.tier(conn, run.usecase_id), run.mode)
        bodies = [rule.board] if rule.board else []
        if rule.external:
            check = f"external:{rule.external}"
            with span(
                "policy",
                "external_approval",
                run_id=run.run_id,
                usecase_id=run.usecase_id,
                terminal_id=run.terminal_id,
            ):
                applies = self.policy.evaluate(
                    rule.external_when or "true",
                    EvalContext(run.terminal_id, check, run.run_id, run.usecase_id),
                ).passed
            if applies:
                bodies.append(rule.external)
        if bodies:
            store.insert_activity(
                conn,
                run.run_id,
                "sign_off",
                "orchestrator",
                ORCHESTRATOR_ID,
                now,
                now,
                "notified",
                {"bodies": bodies},
            )
        return bodies

    def _store_artifacts(self, conn: Connection, run: RunRow, signal: Signal) -> RunRow:
        """Agent results and escalation completion become artifact versions (005 FR-008, FR-009);
        the run's inline artifacts are the latest versions' content."""
        artifacts = dict(signal.payload.get("artifacts") or {})
        entry = self.entry(run.terminal_id, run.spec_version)
        if signal.actor_type == ActorType.AGENT:
            producer = Producer("agent", signal.actor_id, attempt=run.auto_retries + 1)
        else:
            producer = Producer("person", signal.actor_id)
        files = signal.payload.get("attachments") or {}
        changes = {
            aid: Change(
                json_safe(rows),
                tuple(
                    NewAttachment(
                        FileRef(f["content_hash"], int(f["size"]), f["media_type"]), f["name"]
                    )
                    for f in files.get(aid, ())
                ),
            )
            for aid, rows in artifacts.items()
        }
        written = versions.record(conn, run.run_id, entry.spec, changes, producer, put_structured)
        citations = signal.payload.get("citations") or []
        if citations and signal.actor_type == ActorType.AGENT:
            latest = {
                v["artifact_id"]: v["version"]
                for v in ledger_store.latest_versions(conn, run.run_id)
            }
            for c in citations:
                version = written.get(c["artifact"], latest.get(c["artifact"]))
                if version is not None:
                    ledger_store.insert_citation(
                        conn, run.run_id, int(version), c, self.clock.now()
                    )
        return replace(run, artifacts={**run.artifacts, **json_safe(artifacts)})

    def _write_ledger(
        self,
        conn: Connection,
        run: RunRow,
        entry: RegistryEntry,
        emitted: Mapping[str, Any],
        now: datetime,
    ) -> tuple[str, dict[str, Any]]:
        """Version-2 record (005 contracts/record.md): artifacts by version and content hash,
        profile version and package binding, chained to the use case's previous record."""
        store.load_usecase(conn, run.usecase_id, lock=True)  # one chain per use case (R-09)
        previous = store.latest_ledger_hash(conn, run.usecase_id)
        if not store_versions_exist(conn, run.run_id) and run.artifacts:
            # A run opened before feature 005: its inline artifacts become version 1.
            changes = {aid: Change(rows) for aid, rows in run.artifacts.items()}
            producer = Producer("agent", f"agent:{run.run_id}")
            versions.record(conn, run.run_id, entry.spec, changes, producer, put_structured)
        entries = versions.ledger_entries(conn, run.run_id, entry.spec)
        emitted_refs = versions.enrich_emitted(json_safe(emitted), entries)
        waiver = store.load_waiver(conn, run.pending_waiver_id) if run.pending_waiver_id else None

        def record_of(terminal: str) -> Mapping[str, Any] | None:
            if terminal == run.terminal_id:
                return run.artifacts
            return store.latest_closed_artifacts(conn, run.usecase_id, terminal) or None

        content = build_v2(
            run_id=run.run_id,
            usecase_id=run.usecase_id,
            terminal_id=run.terminal_id,
            spec_version=run.spec_version,
            spec_hash=entry.content_hash,
            trigger={
                "event_type": run.trigger_event_type,
                "event_id": None if run.trigger_event_id is None else str(run.trigger_event_id),
                "context": run.trigger_context,
            },
            final_status=str(run.final_status),
            decisions=json_safe(store.sign_offs(conn, run.run_id)),
            recommendation=run.recommendation,
            control_results=run.control_results,
            clarifications=json_safe(store.clarifications(conn, run.run_id)),
            waiver=json_safe(waiver),
            emitted=emitted_refs,
            profile_version=run.profile_version,
            artifacts=entries,
            bound_to=json_safe(resolve_bound_to(entry.spec, record_of)),
        )
        key = spec_view.ledger_key(entry.spec, run.usecase_id, f"run-{run.run_number}")
        record = make_record(
            ledger_key=key, content=json_safe(content), previous_record_hash=previous
        )
        store.insert_ledger_record(conn, record, now)
        return key, emitted_refs

    def _schedule_review(
        self, conn: Connection, run: RunRow, entry: RegistryEntry, now: datetime
    ) -> None:
        schedule = spec_view.review_schedule(entry.spec, self.tier(conn, run.usecase_id))
        if schedule is not None:
            interval = durations.review_interval(schedule)
            store.insert_timer(conn, run.run_id, "review_due", now + self.scaled(interval))

    def _end_lifecycle(
        self,
        conn: Connection,
        run: RunRow,
        signal: Signal,
        event_type: str,
        status: str,
        now: datetime,
    ) -> None:
        """FR-018c: close the other active runs; the use case ends unless retirement follows."""
        reason = "lifecycle terminated" if status == "terminate" else "lifecycle closed"
        for other in store.runs_of_usecase(conn, run.usecase_id):
            if other.run_id != run.run_id and other.state != RunState.CLOSED:
                self.apply_in(
                    conn,
                    other.run_id,
                    Signal(
                        SignalKind.LIFECYCLE_ENDED,
                        ActorType.HUMAN,
                        signal.actor_id,
                        {"comment": reason},
                    ),
                )
        pinned = {
            tid: self.entry(tid, version).spec
            for tid, version in store.pins(conn, run.usecase_id).items()
        }
        if status == "terminate" and routing.subscribers(pinned, event_type):
            return  # retirement runs next; the use case ends when it closes
        store.end_usecase(
            conn, run.usecase_id, "terminated" if status == "terminate" else "closed", now
        )

    # -------------------------------------------------------------- advance

    def advance(self) -> bool:
        """Run one automatic step of some run; ``False`` when none is due."""
        now = self.clock.now()
        with self.engine.begin() as conn:
            leased = store.lease_next_automatic(conn, now, now + self.scaled_lease())
            if leased is None:
                return False
            run_id, interrupted = leased
            if interrupted:
                try:
                    run = self.apply_in(
                        conn,
                        run_id,
                        Signal(
                            SignalKind.STEP_INTERRUPTED, ActorType.ORCHESTRATOR, ORCHESTRATOR_ID
                        ),
                    )
                except InvalidTransition:
                    return True
                if run.state not in _STEP_BY_STATE:
                    return True
                store.set_lease(conn, run_id, now + self.scaled_lease())
        with self.engine.connect() as conn:
            loaded = store.load_run(conn, run_id)
            if loaded is None:
                raise UnknownRun(run_id)
            run = loaded
            entry = self.entry(run.terminal_id, run.spec_version)
            started = self.clock.now()
            step = self._step(conn, run, entry)  # reads what the step needs
        signal = step()  # 006: the agent or reviewer runs with no database connection held
        if signal.payload.get("result") == "model_unavailable" and self._defer(
            run, signal, started
        ):
            return True
        try:
            with self.engine.begin() as conn:
                self.apply_in(
                    conn, run_id, signal, expected_version=run.version, started_at=started
                )
        except (StaleRun, InvalidTransition) as exc:
            with self.engine.begin() as conn:
                store.insert_activity(
                    conn,
                    run_id,
                    _STEP_BY_STATE.get(run.state, "controls"),
                    signal.actor_type.value,
                    signal.actor_id,
                    started,
                    self.clock.now(),
                    "stale",
                    {"reason": str(exc)},
                )
        return True

    def _control_results(self, run: RunRow, spec: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "id": check.id,
                "passed": result.passed,
                "blocking": check.blocking,
                "reason": result.reason,
                "synthetic": result.synthetic,
            }
            for check in spec_view.controls(spec)
            for result in (
                self.policy.evaluate(
                    check.expression, self._eval(run, check.id, run.auto_retries + 1)
                ),
            )
        ]

    def _defer(self, run: RunRow, signal: Signal, started: datetime) -> bool:
        """006 FR-006: during a full outage, wait with back-off instead of signalling.

        Returns False once the outage limit has passed, so the signal escalates the run.
        """
        now = self.clock.now()
        since = run.model_unavailable_since or now
        if now - since >= self.config.model_outage_limit:
            return False
        with self.engine.begin() as conn:
            done = store.deferrals_since(conn, run.run_id, since)
            backoff = min(self.config.outage_backoff * (2**done), self.config.outage_backoff_max)
            store.defer_for_outage(conn, run.run_id, since, now + backoff)
            store.insert_activity(
                conn,
                run.run_id,
                _STEP_BY_STATE.get(run.state, "build"),
                signal.actor_type.value,
                signal.actor_id,
                started,
                now,
                "deferred",
                {
                    "until": (now + backoff).isoformat(),
                    "detail": str(signal.payload.get("detail"))[:200],
                },
            )
        return True

    def scaled_lease(self) -> timedelta:
        return self.config.lease

    def _step(self, conn: Connection, run: RunRow, entry: RegistryEntry) -> Callable[[], Signal]:
        """Read the step's inputs on ``conn``; return the call that produces the signal.

        The returned call runs after the connection is released (006 research R-07), so a model
        call never holds a connection open in a transaction.
        """
        spec = entry.spec
        if run.state == RunState.BUILDING:
            context = self._build_context(conn, run, spec)
            return lambda: self._build(run, context)
        if run.state == RunState.REVIEWING and not run.controls_pending:
            review_context = ReviewContext(
                run.run_id,
                run.terminal_id,
                spec_view.checklist_items(spec),
                run.artifacts,
                tuple(run.control_results),
                tuple(json_safe(store.clarifications(conn, run.run_id))),
            )
            return lambda: self._review(run, review_context)
        return lambda: self._checks(run, spec)

    def _ids(self, run: RunRow) -> dict[str, str]:
        return {"run_id": run.run_id, "usecase_id": run.usecase_id, "terminal_id": run.terminal_id}

    def _build(self, run: RunRow, context: BuildContext) -> Signal:
        with span("agent", "build", **self._ids(run)):
            result = self.agent.build(context)
        return Signal(
            SignalKind.AGENT_RESULT,
            ActorType.AGENT,
            f"agent:{run.run_id}",
            _agent_payload(result),
        )

    def _review(self, run: RunRow, context: ReviewContext) -> Signal:
        with span("reviewer", "review", **self._ids(run)):
            review = self.reviewer.review(context)
        return Signal(
            SignalKind.REVIEW_RESULT,
            ActorType.REVIEWER,
            f"reviewer:{run.run_id}",
            _review_payload(review),
        )

    def _checks(self, run: RunRow, spec: Mapping[str, Any]) -> Signal:
        """Prerequisites, controls, and the re-check after an edit (policy engine only)."""
        ids_ = self._ids(run)
        if run.state == RunState.OPENED:
            with span("policy", "prerequisites", **ids_):
                results = [
                    (check, self.policy.evaluate(check.expression, self._eval(run, check.id)))
                    for check in spec_view.prerequisites(spec)
                ]
            blocked = [c.id for c, r in results if not r.passed and c.blocking]
            warned = [c.id for c, r in results if not r.passed and not c.blocking]
            return Signal(
                SignalKind.PREREQUISITES_RESULT,
                ActorType.ORCHESTRATOR,
                ORCHESTRATOR_ID,
                {"met": not blocked, "blocked_ids": blocked, "warned_ids": warned},
            )
        if run.controls_pending:  # 005: re-check an edit's content before anyone decides
            with span("policy", "controls", **ids_):
                rechecked = self._control_results(run, spec)
            return Signal(
                SignalKind.CONTROLS_RECHECKED,
                ActorType.ORCHESTRATOR,
                ORCHESTRATOR_ID,
                {"results": rechecked},
            )
        with span("policy", "controls", **ids_):
            control_results = self._control_results(run, spec)
        failed = [c["id"] for c in control_results if not c["passed"] and c["blocking"]]
        return Signal(
            SignalKind.CONTROLS_RESULT,
            ActorType.ORCHESTRATOR,
            ORCHESTRATOR_ID,
            {"passed": not failed, "failed_blocking_ids": failed, "results": control_results},
        )

    def _eval(self, run: RunRow, check_id: str, attempt: int | None = None) -> EvalContext:
        # Evidence (run, terminals, intake, ...) is read by the policy engine's provider.
        return EvalContext(run.terminal_id, check_id, run.run_id, run.usecase_id, attempt=attempt)

    def _build_context(
        self, conn: Connection, run: RunRow, spec: Mapping[str, Any]
    ) -> BuildContext:
        usecase = store.load_usecase(conn, run.usecase_id)
        if usecase is None:
            raise UnknownRun(run.usecase_id)
        return BuildContext(
            run_id=run.run_id,
            terminal_id=run.terminal_id,
            spec=spec,
            usecase={
                "usecase_id": usecase.usecase_id,
                "name": usecase.name,
                "intake_text": usecase.intake_text,
                "risk_tier": usecase.risk_tier,
                "mode": run.mode,
            },
            trigger={"event_type": run.trigger_event_type, **run.trigger_context},
            previous_artifacts=store.latest_closed_artifacts(conn, run.usecase_id, run.terminal_id),
            clarifications=tuple(json_safe(store.clarifications(conn, run.run_id))),
            attempt=run.auto_retries + 1,
            failed_controls=tuple(c for c in run.control_results if not c.get("passed")),
        )


def _agent_payload(result: object) -> dict[str, Any]:
    if isinstance(result, Artifacts):
        payload: dict[str, Any] = {"result": "artifacts", "artifacts": json_safe(result.artifacts)}
        if result.citations:  # 008: recorded with the versions they support
            payload["citations"] = [asdict(c) for c in result.citations]
        return payload
    if isinstance(result, Clarification):
        return {"result": "clarification", "clarification": _clarification_payload(result)}
    if isinstance(result, BudgetExceeded):
        return {"result": "budget_exceeded", "detail": result.detail}
    if isinstance(result, AttemptFailed):
        return {"result": "failed", "detail": result.reason[:2000]}
    if isinstance(result, ModelUnavailable):
        return {"result": "model_unavailable", "detail": result.detail[:2000]}
    raise TypeError(f"unexpected agent result {type(result).__name__}")


def _review_payload(result: object) -> dict[str, Any]:
    if isinstance(result, Recommendation):
        return {
            "result": "recommendation",
            "recommendation": {
                "status": result.status,
                "checklist_scores": dict(result.checklist_scores),
                "findings": list(result.findings),
                "reason": result.reason,
                "root_cause": result.root_cause,
                "reviewer": result.reviewer,
            },
        }
    if isinstance(result, AttemptFailed):
        return {"result": "failed", "detail": result.reason[:2000]}
    if isinstance(result, ModelUnavailable):
        return {"result": "model_unavailable", "detail": result.detail[:2000]}
    if isinstance(result, Clarification):
        return {"result": "clarification", "clarification": _clarification_payload(result)}
    raise TypeError(f"unexpected review result {type(result).__name__}")


def _clarification_payload(c: Clarification) -> dict[str, Any]:
    return {
        "questions": list(c.questions),
        "addressed_role": c.addressed_role,
        "looked_in": list(c.looked_in),
    }


def _reason(signal: Signal) -> str | None:
    p = signal.payload
    if p.get("result") and p.get("detail"):  # 006: e.g. "failed: missing column kpi_id"
        return f"{p['result']}: {p['detail']}"[:2000]
    for key in ("comment", "trigger", "kind", "event_type", "result", "decision"):
        if p.get(key):
            return str(p[key])
    return None


def _detail(signal: Signal) -> dict[str, Any]:
    keep = (
        "decision",
        "role",
        "root_cause",
        "met",
        "blocked_ids",
        "warned_ids",
        "passed",
        "failed_blocking_ids",
        "result",
        "kind",
        "trigger",
        "event_type",
        "approve",
        "clarification_id",
        "edited",
    )
    return json_dict({k: signal.payload[k] for k in keep if k in signal.payload})
