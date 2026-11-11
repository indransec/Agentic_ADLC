"""Orchestrator service operations: the only entry point for human and admin actions
(contracts/service-operations.md; SA §8.1; FR-034). Feature 007 exposes them over HTTP.

Each operation checks who is acting against the pinned spec, validates the decision, and
applies one signal in one transaction. Nothing is written when an operation is refused.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Connection

from adlc.identity.protocol import Person
from adlc.inbox import rules
from adlc.orchestration import ids, routing, spec_view, store
from adlc.orchestration.engine import PostgresTerminalRun, StaleRun, UnknownRun
from adlc.orchestration.states import (
    DECISIONS,
    ActorType,
    InvalidTransition,
    Signal,
    SignalKind,
)
from adlc.orchestration.store import RunRow, UseCaseRow

__all__ = [
    "Actor",
    "AlreadyAnswered",
    "InvalidDecision",
    "InvalidTransition",
    "NoActiveSpecs",
    "NotAuthorised",
    "NotDeadLettered",
    "OrchestratorService",
    "StaleRun",
    "UnknownEvent",
    "UnknownRun",
]

SUBMIT_REASON = "pinned at submit"


class NotAuthorised(Exception):
    pass


class InvalidDecision(Exception):
    pass


class NoActiveSpecs(Exception):
    pass


class AlreadyAnswered(Exception):
    pass


class UnknownEvent(Exception):
    pass


class NotDeadLettered(Exception):
    pass


@dataclass(frozen=True)
class Actor:
    """A signed-in person, or a system identity (monitoring, agents)."""

    account_name: str
    roles: frozenset[str] = field(default_factory=frozenset)
    kind: str = "human"  # human | system | agent

    @classmethod
    def from_person(cls, person: Person) -> "Actor":
        return cls(person.account_name, person.roles)

    @classmethod
    def system(cls, name: str) -> "Actor":
        return cls(name, frozenset(), "system")


class OrchestratorService:
    def __init__(self, runs: PostgresTerminalRun, deadletter_role: str) -> None:
        self.runs = runs
        self.deadletter_role = deadletter_role

    @property
    def _now(self) -> Any:
        return self.runs.clock.now()

    def _human(self, actor: Actor) -> None:
        if actor.kind != "human":
            raise NotAuthorised("only a person can take this decision")

    # -------------------------------------------------------------- use cases

    def submit_usecase(self, actor: Actor, name: str, intake_text: str) -> str:
        self._human(actor)
        if not name.strip() or len(name) > 200:
            raise InvalidDecision("name must be 1 to 200 characters")
        with self.runs.engine.begin() as conn:
            versions = store.active_spec_versions(conn)
            if not versions:
                raise NoActiveSpecs("no active terminal specs are registered")
            usecase = ids.usecase_id(store.next_usecase_number(conn))
            store.insert_usecase(conn, usecase, name.strip(), intake_text, actor.account_name)
            for terminal_id, version in versions:
                store.insert_pin(conn, usecase, terminal_id, version, SUBMIT_REASON)
            store.insert_event(
                conn,
                event_id=ids.uuid7(),
                event_type="usecase.submitted",
                usecase_id=usecase,
                correlation_id=ids.correlation_id(usecase),
                causation_run_id=None,
                payload={"usecase_id": usecase, "submitted_by": actor.account_name},
                now=self._now,
            )
        return usecase

    def get_usecase(self, usecase_id: str) -> UseCaseRow | None:
        with self.runs.engine.connect() as conn:
            return store.load_usecase(conn, usecase_id)

    def get_run(self, run_id: str) -> RunRow | None:
        with self.runs.engine.connect() as conn:
            return store.load_run(conn, run_id)

    def list_runs(self, usecase_id: str) -> list[RunRow]:
        with self.runs.engine.connect() as conn:
            return store.runs_of_usecase(conn, usecase_id)

    # -------------------------------------------------------------- decisions

    def decide(
        self,
        actor: Actor,
        run_id: str,
        decision: str,
        *,
        comment: str | None = None,
        root_cause: str | None = None,
        reason: str | None = None,
        fields: Mapping[str, Any] | None = None,
        target_terminal: str | None = None,
        expected_version: int | None = None,
    ) -> RunRow:
        self._human(actor)
        fields = dict(fields or {})
        with self.runs.engine.begin() as conn:
            run = self._run(conn, run_id)
            version = run.version if expected_version is None else expected_version
            if run.version != version:
                raise StaleRun(f"{run_id} is at version {run.version}, not {version}")
            spec = self.runs.entry(run.terminal_id, run.spec_version).spec
            role = self._decision_role(conn, actor, run, spec, decision)
            self._validate(
                conn, run, spec, decision, comment, root_cause, reason, fields, target_terminal
            )
            payload = {
                "decision": decision,
                "role": role,
                "comment": comment,
                "root_cause": root_cause,
                "reason": reason,
                "fields": fields,
                "target_terminal": target_terminal,
            }
            return self.runs.apply_in(
                conn,
                run_id,
                Signal(SignalKind.DECIDE, ActorType.HUMAN, actor.account_name, payload),
                expected_version=version,
            )

    def _run(self, conn: Connection, run_id: str) -> RunRow:
        run = store.load_run(conn, run_id)
        if run is None:
            raise UnknownRun(run_id)
        return run

    def _decision_role(
        self, conn: Connection, actor: Actor, run: RunRow, spec: Mapping[str, Any], decision: str
    ) -> str:
        if decision not in DECISIONS:
            raise InvalidDecision(f"unknown decision {decision!r}")
        if decision == "terminate":
            allowed = spec_view.outcome_set_by(spec, "terminate") or self._sign_off_roles(
                conn, run, spec
            )
        else:
            allowed = self._sign_off_roles(conn, run, spec)
        held = sorted(actor.roles & allowed)
        if not held:
            raise NotAuthorised(
                f"{actor.account_name} holds none of {sorted(allowed)} for {run.terminal_id}"
            )
        if decision != "pass":
            return held[0]
        ctx = self.runs.context(conn, run)
        rule_held = [r for r in held if r in ctx.rule_roles]
        covered = {role for _, role in ctx.approvals}
        plus_open = [r for r in held if r in ctx.required_plus_roles and r not in covered]
        rule_people = {person for person, role in ctx.approvals if role in ctx.rule_roles}
        if plus_open and (len(rule_people) >= ctx.min_approvers or not rule_held):
            return plus_open[0]
        return rule_held[0] if rule_held else held[0]

    def _sign_off_roles(
        self, conn: Connection, run: RunRow, spec: Mapping[str, Any]
    ) -> frozenset[str]:
        ctx = self.runs.context(conn, run)
        return ctx.rule_roles | ctx.required_plus_roles

    def _validate(
        self,
        conn: Connection,
        run: RunRow,
        spec: Mapping[str, Any],
        decision: str,
        comment: str | None,
        root_cause: str | None,
        reason: str | None,
        fields: Mapping[str, Any],
        target_terminal: str | None,
    ) -> None:
        if spec_view.outcome_not_allowed(spec, decision):
            raise InvalidDecision(f"{decision} is not allowed for {run.terminal_id}")
        recommended = (run.recommendation or {}).get("status")
        if recommended and recommended != decision and decision != "terminate" and not reason:
            raise InvalidDecision(f"the reviewer recommended {recommended}; a reason is required")
        if decision == "terminate":
            if not (comment or reason):
                raise InvalidDecision("terminate needs a reason")
            return
        if decision == "rework":
            self._validate_rework(conn, run, spec, comment, root_cause, fields, target_terminal)
            return
        route = self.runs.registry.outcome_route(
            run.terminal_id, decision, version=run.spec_version
        )
        if route is None or route.kind == "disabled":
            raise InvalidDecision(f"{decision} has no route for {run.terminal_id}")
        if decision == "exception":
            missing = [
                f for f in spec_view.outcome_requires(spec, "exception") if not fields.get(f)
            ]
            if missing:
                raise InvalidDecision(f"an exception needs {', '.join(missing)}")
            if "expiry" in fields:
                try:
                    expiry = date.fromisoformat(str(fields["expiry"]))
                except ValueError as exc:
                    raise InvalidDecision("expiry must be a date (YYYY-MM-DD)") from exc
                if expiry <= self._now.date():
                    raise InvalidDecision("expiry must be in the future")
        if decision == "pass":
            emitted = routing.emitted_values(
                spec, run.artifacts, {"usecase_id": run.usecase_id}, fields
            )
            if emitted.missing:
                raise InvalidDecision(f"a pass must supply {', '.join(emitted.missing)}")
        if route.kind == "template":
            alternative = fields.get("alternative")
            if alternative:
                if alternative not in route.alternatives:
                    raise InvalidDecision(f"{alternative} is not an alternative route")
                return
            reentry = routing.resolve_template(route.destination, run.terminal_id, run.artifacts)
            if reentry is None or reentry not in spec_view.reentry_terminals(spec):
                raise InvalidDecision(
                    f"re-entry {reentry!r} is not a change-class re-entry terminal"
                )

    def _validate_rework(
        self,
        conn: Connection,
        run: RunRow,
        spec: Mapping[str, Any],
        comment: str | None,
        root_cause: str | None,
        fields: Mapping[str, Any],
        target_terminal: str | None,
    ) -> None:
        if not comment or not root_cause:
            raise InvalidDecision("rework needs a comment and a root cause")
        allowed = spec_view.rework_causes(spec) or self._catalogue_root_causes()
        if root_cause not in allowed:
            raise InvalidDecision(
                f"root cause {root_cause!r} is not routed; allowed: {', '.join(allowed)}"
            )
        route = self.runs.registry.outcome_route(
            run.terminal_id, "rework", root_cause, run.spec_version
        )
        if route is None:
            raise InvalidDecision(f"rework {root_cause} has no route")
        resolver = self.runs.destination_kind(route.destination) == "terminal_resolver"
        if resolver and (
            not target_terminal or target_terminal not in store.pins(conn, run.usecase_id)
        ):
            raise InvalidDecision("this rework needs the owning terminal (target_terminal)")
        missing = [
            f
            for f in spec_view.outcome_requires(spec, "rework")
            if f != "owner_comment" and not fields.get(f)
        ]
        if missing:
            raise InvalidDecision(f"rework needs {', '.join(missing)}")

    def _catalogue_root_causes(self) -> tuple[str, ...]:
        catalogue = self.runs.registry.catalogue("root_causes")
        items = (catalogue.content if catalogue else {}).get("root_causes", [])
        return tuple(str(i["id"]) for i in items)

    def decide_waiver(
        self, actor: Actor, waiver_id: str, approve: bool, comment: str | None = None
    ) -> RunRow:
        self._human(actor)
        with self.runs.engine.begin() as conn:
            waiver = store.load_waiver(conn, waiver_id)
            if waiver is None:
                raise InvalidTransition(f"unknown waiver {waiver_id}")
            run = self._run(conn, str(waiver["run_id"]))
            spec = self.runs.entry(run.terminal_id, run.spec_version).spec
            approvers = rules.waiver_approvers(spec)
            if not actor.roles & approvers:
                raise NotAuthorised(f"waiver approval needs one of {sorted(approvers)}")
            if actor.account_name == waiver["proposed_by"]:
                raise NotAuthorised("the waiver approver must differ from the proposer")
            if run.pending_waiver_id != waiver_id:
                raise InvalidTransition(f"{waiver_id} is not pending")
            return self.runs.apply_in(
                conn,
                run.run_id,
                Signal(
                    SignalKind.WAIVER_DECISION,
                    ActorType.HUMAN,
                    actor.account_name,
                    {"approve": approve, "comment": comment},
                ),
            )

    # -------------------------------------------------------------- clarifications and escalations

    def answer_clarification(self, actor: Actor, clarification_id: str, answers: Any) -> RunRow:
        self._human(actor)
        with self.runs.engine.begin() as conn:
            round_ = store.load_clarification(conn, clarification_id)
            if round_ is None:
                raise InvalidTransition(f"unknown clarification {clarification_id}")
            if round_["answered_by"] is not None:
                raise AlreadyAnswered(clarification_id)
            if not rules.can_answer(actor, round_["addressed_role"]):
                raise NotAuthorised(f"only {round_['addressed_role']} may answer")
            store.insert_answer(conn, clarification_id, actor.account_name, answers, self._now)
            return self.runs.apply_in(
                conn,
                str(round_["run_id"]),
                Signal(
                    SignalKind.CLARIFICATION_ANSWERED,
                    ActorType.HUMAN,
                    actor.account_name,
                    {"clarification_id": clarification_id},
                ),
            )

    def complete_escalation(
        self,
        actor: Actor,
        run_id: str,
        artifacts: Mapping[str, Any],
        expected_version: int | None = None,
    ) -> RunRow:
        self._human(actor)
        with self.runs.engine.begin() as conn:
            run = self._run(conn, run_id)
            spec = self.runs.entry(run.terminal_id, run.spec_version).spec
            if not rules.can_complete_escalation(actor, spec):
                raise NotAuthorised(
                    f"escalation completion needs one of {sorted(rules.accountable(spec))}"
                )
            merged = {**run.artifacts, **dict(artifacts)}
            return self.runs.apply_in(
                conn,
                run_id,
                Signal(
                    SignalKind.ESCALATION_COMPLETED,
                    ActorType.HUMAN,
                    actor.account_name,
                    {"artifacts": merged},
                ),
                expected_version=expected_version,
            )

    # -------------------------------------------------------------- operational events

    def raise_operational_event(
        self, actor: Actor, usecase_id: str, event_name: str, payload: Mapping[str, Any]
    ) -> UUID:
        if actor.kind not in ("system", "agent"):
            raise NotAuthorised("operational events are raised by monitoring, not by people")
        with self.runs.engine.begin() as conn:
            pinned = store.pins(conn, usecase_id)
            source = None
            for terminal_id, version in sorted(pinned.items()):
                spec = self.runs.entry(terminal_id, version).spec
                event_type = routing.operational_event_type(terminal_id, event_name)
                if event_type in spec_view.raised_events(
                    spec
                ) and "raise_event" in spec_view.status_rights(spec, "agent"):
                    source = terminal_id
                    break
            if source is None:
                raise UnknownEvent(f"no monitor of {usecase_id} raises {event_name}")
            event_id = ids.uuid7()
            store.insert_event(
                conn,
                event_id=event_id,
                event_type=routing.operational_event_type(source, event_name),
                usecase_id=usecase_id,
                correlation_id=ids.correlation_id(usecase_id),
                causation_run_id=store.active_run(conn, usecase_id, source),
                payload={**dict(payload), "raised_by": actor.account_name},
                now=self._now,
            )
            return event_id

    # -------------------------------------------------------------- dead letters

    def _coe(self, actor: Actor) -> None:
        if self.deadletter_role not in actor.roles:
            raise NotAuthorised(f"dead letters need role {self.deadletter_role}")

    def list_dead_letters(self, actor: Actor) -> Sequence[Mapping[str, Any]]:
        self._coe(actor)
        with self.runs.engine.connect() as conn:
            return store.dead_letters(conn)

    def requeue(self, actor: Actor, event_id: UUID) -> None:
        self._coe(actor)
        with self.runs.engine.begin() as conn:
            if not store.requeue(conn, event_id, actor.account_name, self._now):
                raise NotDeadLettered(str(event_id))
