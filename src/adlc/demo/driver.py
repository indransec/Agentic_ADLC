"""The demo driver (feature 014, research R-01 to R-03): runs a demo script on the platform.

For each step it waits until the step's terminal has a run that needs people, takes the step's
actions (``auto``) or tells the presenter what to do and waits until it is done, then checks the
step's expectation. Human actions go through the platform's service operations as the named roles
(the replayer's operations: every needed approver passes, an exception's waiver is approved by
another person, a clarification is answered by its addressed role). Faults are asked of the host
wrapper (operator access to the pilot); the monitors are evaluated after one. Nothing here names a
terminal or a use case: they come from the script and the reference.

020: with a board actor (the board sync on), every human step is a board change made as the named
demo person (``adlc.demo.board``), and the presenter is told the item's address and the values;
steps that exist only on the board (D-12, D-13) are skipped when the sync is off.
"""

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import text

from adlc.agents.replay import REPLAY_REASON, Reference, Replayer
from adlc.dashboard.service import DashboardService
from adlc.demo.board import BoardActor, BoardStepFailed, Write
from adlc.demo.script import MOMENTS, Action, DemoScript, Step
from adlc.engagement import store as board_store
from adlc.inbox.changes import ChangeService
from adlc.inbox.rules import waiver_approvers
from adlc.orchestration import routing
from adlc.orchestration.monitors import MonitorEvaluator
from adlc.orchestration.service import Actor
from adlc.orchestration.states import RunState
from adlc.orchestration.store import RunRow

NEEDS_PEOPLE = (
    RunState.AWAITING_SIGN_OFF,
    RunState.ESCALATED,
    RunState.AWAITING_CLARIFICATION,
    RunState.BLOCKED,
)
DEFAULT_ROUNDS = 400


class StepFailed(Exception):
    """A step did not reach its expectation; the message says why and how to resume."""


class Io(Protocol):
    """How the driver talks to the presenter and the host wrapper."""

    def say(self, text: str) -> None: ...

    def fault(self, name: str, action: str) -> None: ...

    def pause(self) -> None: ...


@dataclass
class StepResult:
    number: int
    usecase: str
    terminal: str
    proves: tuple[str, ...]
    outcome: str
    run_id: str | None
    seconds: float
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class DemoReport:
    steps: list[StepResult]
    usecases: dict[str, str]

    @property
    def ok(self) -> bool:
        return bool(self.steps) and all(s.outcome == "ok" for s in self.steps)

    def moments(self) -> dict[str, list[dict[str, Any]]]:
        found: dict[str, list[dict[str, Any]]] = {m: [] for m in MOMENTS}
        for step in self.steps:
            for moment in step.proves:
                found.setdefault(moment, [])  # 020: the board moments of steps that ran
                if step.outcome == "ok":
                    found[moment].append(
                        {"step": step.number, "run_id": step.run_id, **step.evidence}
                    )
        return found

    def markdown(self) -> str:
        lines = [
            "# Demo report",
            "",
            "| Step | Use case | Terminal | Proves | Outcome | Run | Seconds |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for s in self.steps:
            lines.append(
                f"| {s.number} | {self.usecases.get(s.usecase, s.usecase)} | {s.terminal} | "
                f"{', '.join(s.proves)} | {s.outcome} | {s.run_id or '-'} | {s.seconds:.1f} |"
            )
        lines += ["", "| Moment | Shown by |", "| --- | --- |"]
        for moment, shown in self.moments().items():
            proof = "; ".join(f"step {p['step']} ({p['run_id']})" for p in shown) or "NOT SHOWN"
            lines.append(f"| {moment} | {proof} |")
        return "\n".join(lines) + "\n"

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "usecases": self.usecases,
            "steps": [s.__dict__ for s in self.steps],
            "moments": self.moments(),
        }


class DemoDriver:
    def __init__(
        self,
        script: DemoScript,
        references: Mapping[str, Reference],
        replayer: Replayer,
        changes: ChangeService,
        monitors: MonitorEvaluator,
        io: Io,
        *,
        auto: bool,
        rounds: int = DEFAULT_ROUNDS,
        clock: Callable[[], float] = time.monotonic,
        board: BoardActor | None = None,
        reconcile: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        """``board``: 020, the people act on the board (the sync on); ``reconcile``: the CoE's
        reconciliation (D-13 in auto mode)."""
        self.script, self.references, self.replayer = script, references, replayer
        self.changes, self.monitors, self.io, self.auto = changes, monitors, io, auto
        self.rounds, self.clock = rounds, clock
        self.service, self.runs, self.drain, self.people = (
            replayer.service,
            replayer.runs,
            replayer.drain,
            replayer.people,
        )
        self.usecases: dict[str, str] = {}
        self.board, self.reconcile = board, reconcile
        self._drifted: tuple[int, str, str] | None = None  # item, field, the drifted value

    # -------------------------------------------------------------- driving

    def run(self, from_step: int = 1) -> DemoReport:
        report = DemoReport([], self.usecases)
        self._resume()
        for step in self.script.steps:
            if step.number < from_step:
                continue
            if step.board_only and self.board is None:
                self.io.say(
                    f"Step {step.number} skipped: it shows {', '.join(step.proves)}, which needs "
                    "the board (the board sync is off)."
                )
                continue
            started = self.clock()
            self.io.say(f"Step {step.number} ({step.terminal}): {step.say}")
            try:
                run, evidence = self._step(step)
            except StepFailed as exc:
                report.steps.append(
                    StepResult(
                        step.number,
                        step.usecase,
                        step.terminal,
                        step.proves,
                        f"failed: {exc}",
                        None,
                        self.clock() - started,
                    )
                )
                self.io.say(
                    f"Step {step.number} failed: {exc}. Fix the cause, then resume with "
                    f"--from-step {step.number}."
                )
                break
            report.steps.append(
                StepResult(
                    step.number,
                    step.usecase,
                    step.terminal,
                    step.proves,
                    "ok",
                    run.run_id if run else None,
                    self.clock() - started,
                    evidence,
                )
            )
        return report

    def _resume(self) -> None:
        """Use cases already started by an earlier run of the script (``--from-step``)."""
        with self.runs.engine.connect() as conn:
            for key in self.script.usecases:
                found = conn.execute(
                    text(
                        "SELECT usecase_id FROM usecase WHERE name = :n "
                        "ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"n": self._name(key)},
                ).scalar()
                if found is not None:
                    self.usecases[key] = str(found)

    def _name(self, key: str) -> str:
        reference = self.references[self.script.usecases[key]]
        return (
            reference.name
            if key == next(iter(self.script.usecases))
            else f"{reference.name} ({key})"
        )

    def _step(self, step: Step) -> tuple[RunRow | None, dict[str, Any]]:
        if step.board_only:
            return self._latest(step), self._board_step(step)
        acted: RunRow | None = None
        for action in step.actions:
            if action.kind == "submit":
                self._submit(step, action)
                continue
            if action.kind == "fault":
                self.io.fault(
                    str(action.params["name"]), str(action.params.get("action", "trigger"))
                )
                self.drain()
                # 014 rehearsal finding: only the demo's use cases; on a database with earlier
                # use cases, their monitors would open runs that use up the rehearsed replies
                self.monitors.tick(set(self.usecases.values()))
                continue
            run = self._wait_for_people(step)
            acted = run
            try:
                if self.board is not None:
                    self._board_act(run, action)
                elif self.auto:
                    self._act(run, action)
                else:
                    self._presenter(run, action)
            except StepFailed:
                raise
            except BoardStepFailed as exc:
                raise StepFailed(str(exc)) from exc
            except Exception as exc:  # the platform refused the action: report, never crash
                raise StepFailed(
                    f"{action.kind} on {run.run_id} ({run.state}) was refused: {exc}"
                ) from exc
            self.drain()
        last = acted or self._latest(step)
        return last, self._check(step, last)

    # -------------------------------------------------------------- waiting

    def _usecase(self, step: Step) -> str:
        if step.usecase not in self.usecases:
            raise StepFailed(f"use case {step.usecase} was not submitted (run its first step)")
        return self.usecases[step.usecase]

    def _latest(self, step: Step) -> RunRow | None:
        runs = [
            r for r in self.service.list_runs(self._usecase(step)) if r.terminal_id == step.terminal
        ]
        return max(runs, key=lambda r: r.run_number) if runs else None

    def _wait_for_people(self, step: Step) -> RunRow:
        for _ in range(self.rounds):
            # 014 rehearsal finding: the driver is the only worker, so it evaluates the declared
            # monitors at their interval while it waits (a drift shows once the window moves)
            self.monitors.tick_if_due(set(self.usecases.values()))
            self.drain()
            run = self._latest(step)
            if run is not None and run.state in NEEDS_PEOPLE and not run.controls_pending:
                return run
            self.io.pause()
        state = self._latest(step)
        raise StepFailed(
            f"{step.terminal} did not reach a state that needs people "
            f"(now {state.state if state else 'no run'})"
        )

    # -------------------------------------------------------------- actions

    def _submit(self, step: Step, action: Action) -> None:
        reference = self.references[self.script.usecases[step.usecase]]
        name = self._name(step.usecase)
        if self.board is not None:
            self._board_submit(step, action, name, reference.intake_text)
            return
        if self.auto:
            person = self.people(str(action.role))[0]
            self.usecases[step.usecase] = self.service.submit_usecase(
                person, name, reference.intake_text
            )
            return
        self.io.say(
            f"As {action.role}: open 'New use case', name it '{name}', paste the intake from "
            f"{reference.id} and submit."
        )
        for _ in range(self.rounds):
            self._resume()
            if step.usecase in self.usecases:
                return
            self.io.pause()
        raise StepFailed(f"no use case named '{name}' was submitted")

    def _act(self, run: RunRow, action: Action) -> None:
        params = action.params
        if action.kind == "pass":
            ref = Reference(
                "demo", "", "", "", {}, {run.terminal_id: dict(params.get("fields") or {})}, {}
            )
            self.replayer._pass(run, ref)
        elif action.kind == "reject":
            self.service.decide(
                self.people(str(action.role))[0],
                run.run_id,
                "rework",
                comment=params.get("comment"),
                root_cause=params.get("root_cause"),
                reason=params.get("reason"),
                fields=dict(params.get("fields") or {}),
            )
        elif action.kind == "answer":
            self.replayer._answer(run, {"any": [str(params["text"])]})
        elif action.kind == "exception":
            self.replayer._exception(run, dict(params.get("fields") or {}))
        elif action.kind == "approve_change":
            role = self.changes.approver()
            approver = self.people(role)[0] if role else None
            waiting = [
                c
                for c in (self.changes.waiting(approver) if approver else [])
                if c["usecase_id"] == run.usecase_id
            ]
            if approver is None or not waiting:
                raise StepFailed("no change request waits for a decision")
            for change in waiting:
                self.changes.decide(approver, change["change_id"], True, "demo: approved")
        elif action.kind == "complete_escalation":
            self.service.complete_escalation(
                self.people(str(action.role))[0], run.run_id, run.artifacts
            )
        elif action.kind == "wait":
            return

    def _presenter(self, run: RunRow, action: Action) -> None:
        """Tell the presenter what to do in the web app, then wait until the run shows it."""
        who = f"As {action.role}" if action.role else "As the role the inbox shows"
        p = action.params
        what = {
            "pass": "open the run from the inbox and pass it (every approver the form asks for)",
            "reject": (
                f"open the run and choose rework: comment '{p.get('comment')}', "
                f"root cause {p.get('root_cause')}"
            ),
            "answer": f"open the clarification from the inbox and answer: {p.get('text')}",
            "exception": (
                "open the run, choose exception with the waiver fields, then have the risk owner "
                "approve the waiver"
            ),
            "approve_change": "open Inbox, Change requests, and approve the change",
            "complete_escalation": "open the escalation from the inbox and complete it",
        }.get(action.kind, action.kind)
        self.io.say(f"{who}: {what} (run {run.run_id}).")
        before = run.version
        for _ in range(self.rounds):
            self.drain()
            current = self.service.get_run(run.run_id)
            if current is not None and (
                current.version != before or current.state == RunState.CLOSED
            ):
                return
            self.io.pause()
        raise StepFailed(f"the presenter did not {action.kind} run {run.run_id}")

    # -------------------------------------------------------------- on the board (020)

    def _board_submit(self, step: Step, action: Action, name: str, intake: str) -> None:
        assert self.board is not None  # noqa: S101 - board mode only
        person = self.people(str(action.role))[0]
        if self.auto:
            self.board.create_usecase(person, name, intake)
        else:
            self.io.say(
                f"As {self.board.user_of(person)}: on the board, create a new "
                f"{self.board.mapping.item('usecase').type} in the area "
                f"'{self.board.mapping.area}' named '{name}', with the intake of the reference "
                "use case as its description."
            )
        for _ in range(self.rounds):  # the board sync registers it
            self._resume()
            if step.usecase in self.usecases:
                return
            self.drain()
            self.io.pause()
        raise StepFailed(f"the board's '{name}' was not registered as a use case")

    def _approvers(self, run: RunRow) -> list[Actor]:
        """A distinct person for each sign-off the run still needs (as the replayer passes)."""
        with self.runs.engine.connect() as conn:
            ctx = self.runs.context(conn, run)
        signed = {person for person, _ in ctx.approvals}
        needed = sorted(ctx.required_plus_roles - {r for _, r in ctx.approvals}) + sorted(
            ctx.rule_roles
        )
        chosen: list[Actor] = []
        for role in needed:
            taken = signed | {a.account_name for a in chosen}
            person = next((a for a in self.people(role) if a.account_name not in taken), None)
            if person is not None:
                chosen.append(person)
        return chosen

    def _board_writes(self, run: RunRow, action: Action) -> list[Write]:
        """What the step's people change on the board, in the mapping's fields."""
        assert self.board is not None  # noqa: S101 - board mode only
        board, params, kind = self.board, action.params, action.kind
        fields = dict(params.get("fields") or {})
        if kind == "pass":
            spec = self.runs.entry(run.terminal_id, run.spec_version).spec
            missing = routing.emitted_values(
                spec, run.artifacts, {"usecase_id": run.usecase_id}, fields
            )
            fields.update({name: f"{name} (demo)" for name in missing.missing})
            recommended = (run.recommendation or {}).get("status")
            reason = None if recommended in (None, "pass") else REPLAY_REASON
            decision = board.decision("pass", reason=reason, values=fields)
            return [Write(a, "run", run.run_id, decision) for a in self._approvers(run)]
        if kind == "reject":
            decision = board.decision(
                "rework",
                comment=params.get("comment"),
                root_cause=params.get("root_cause"),
                reason=params.get("reason"),
                values=fields,
            )
            return [Write(self.people(str(action.role))[0], "run", run.run_id, decision)]
        if kind == "answer":
            with self.runs.engine.connect() as conn:
                open_round = conn.execute(
                    text(
                        "SELECT c.clarification_id, c.addressed_role, c.questions FROM "
                        "clarification_round c LEFT JOIN clarification_answer a "
                        "USING (clarification_id) WHERE c.run_id = :r "
                        "AND a.clarification_id IS NULL"
                    ),
                    {"r": run.run_id},
                ).first()
            if open_round is None:
                return []
            questions = open_round[2]
            count = len(questions) if isinstance(questions, list) else 1
            answer = board.answer(count, str(params["text"]))
            person = self.people(str(open_round[1]))[0]
            return [Write(person, "clarification", str(open_round[0]), answer)]
        if kind == "exception":
            deciders = self._approvers(run)
            if not deciders:
                return []
            spec = self.runs.entry(run.terminal_id, run.spec_version).spec
            decider = deciders[0]
            approver = next(
                (
                    a
                    for role in sorted(waiver_approvers(spec))
                    for a in self.people(role)
                    if a.account_name != decider.account_name
                ),
                None,
            )
            writes = [
                Write(
                    decider,
                    "run",
                    run.run_id,
                    board.decision("exception", reason=REPLAY_REASON, values=fields),
                )
            ]
            if approver is not None:
                waiver = board.decision("approve_waiver", comment="demo: waiver approved")
                writes.append(Write(approver, "run", run.run_id, waiver))
            return writes
        if kind == "complete_escalation":
            decision = board.decision("complete_escalation", comment="demo: completed")
            return [Write(self.people(str(action.role))[0], "run", run.run_id, decision)]
        if kind == "approve_change":
            role = self.changes.approver()
            approver = self.people(role)[0] if role else None
            waiting = [
                c
                for c in (self.changes.waiting(approver) if approver else [])
                if c["usecase_id"] == run.usecase_id
            ]
            if approver is None or not waiting:
                raise StepFailed("no change request waits for a decision")
            decision = board.decision("approve_change", comment="demo: change approved")
            return [Write(approver, "change", str(c["change_id"]), decision) for c in waiting]
        return []  # wait

    def _board_act(self, run: RunRow, action: Action) -> None:
        assert self.board is not None  # noqa: S101 - board mode only
        writes = self._board_writes(run, action)
        if not self.auto:
            for write in writes:
                self.io.say(self.board.instruction(write))
            self._wait_for_run(run, action)
            return
        for write in writes:
            current = self.service.get_run(run.run_id)
            if (
                action.kind == "pass"
                and current is not None
                and current.state != RunState.AWAITING_SIGN_OFF
            ):
                break  # the sign-off rule is met: no further approver is asked
            self.board.apply(write)
            self.drain()

    def _wait_for_run(self, run: RunRow, action: Action) -> None:
        before = run.version
        for _ in range(self.rounds):
            self.drain()
            current = self.service.get_run(run.run_id)
            if current is not None and (
                current.version != before or current.state == RunState.CLOSED
            ):
                return
            self.io.pause()
        raise StepFailed(f"the presenter did not {action.kind} run {run.run_id} on the board")

    def _board_step(self, step: Step) -> dict[str, Any]:
        """D-12 (a change without the right, set back) and D-13 (drift, reconciled)."""
        assert self.board is not None  # noqa: S101 - board mode only
        board = self.board
        evidence: dict[str, Any] = {}
        for action in step.actions:
            params = action.params
            item_kind, field_key = str(params.get("item", "")), str(params.get("field", ""))
            object_id = self._object(step, item_kind) if item_kind else ""
            if action.kind == "board_change":
                name = board.mapping.field(item_kind, field_key)
                write = Write(
                    self.people(str(action.role))[0],
                    item_kind,
                    object_id,
                    {name: str(params["value"])},
                    refusal_expected=True,
                )
                if self.auto:
                    item = board.apply(write)
                else:
                    self.io.say(board.instruction(write))
                    item = self._await_read(item_kind, object_id)
                self.drain()
                evidence.update(item=item, field=name, attempted=str(params["value"]))
            elif action.kind == "drift":
                item, name = board.drift(item_kind, object_id, field_key, str(params["value"]))
                self._drifted = (item, name, str(params["value"]))
                self.io.say(
                    f"The board's {item_kind} item {item} now shows {name} = {params['value']!r},"
                    " out of step with the platform (changed as the service account, which the"
                    " sync reads as its own change: a demo device)."
                )
            elif action.kind == "reconcile":
                evidence.update(self._reconciled())
        self._check_board(step, evidence)
        return evidence

    def _object(self, step: Step, kind: str) -> str:
        if kind == "usecase":
            return self._usecase(step)
        latest = self._latest(step)
        if latest is None:
            raise StepFailed(f"no {step.terminal} run for the {kind} item")
        return latest.run_id

    def _await_read(self, kind: str, object_id: str) -> int:
        assert self.board is not None  # noqa: S101 - board mode only
        item = self.board.item(kind, object_id)
        before = len(self.board._outcomes(item))  # noqa: SLF001 - the actor's own read
        for _ in range(self.rounds):
            self.drain()
            if len(self.board._outcomes(item)) > before:  # noqa: SLF001
                return item
            self.io.pause()
        raise StepFailed(f"no change to the {kind} item {item} was read")

    def _reconciled(self) -> dict[str, Any]:
        with self.runs.engine.connect() as conn:
            last = board_store.reconciliation(conn)
        before = None if last is None else last["id"]
        if self.auto:
            if self.reconcile is None:
                raise StepFailed("no reconciliation is wired for the demo")
            report: dict[str, Any] | None = self.reconcile()
        else:
            self.io.say("As the CoE: open Sync status in the console and press Reconcile now.")
            report = None
            for _ in range(self.rounds):
                with self.runs.engine.connect() as conn:
                    last = board_store.reconciliation(conn)
                if last is not None and last["id"] != before:
                    report = last
                    break
                self.io.pause()
        if report is None:
            raise StepFailed("no reconciliation was run")
        return {"reconciliation": report["id"], "differences": report["differences"]}

    def _check_board(self, step: Step, evidence: dict[str, Any]) -> None:
        assert self.board is not None  # noqa: S101 - board mode only
        expect = step.expect
        if expect.get("reverted"):
            item, name = evidence["item"], evidence["field"]
            now = self.board.service_board.get(item).fields.get(name)
            if now == evidence["attempted"]:
                raise StepFailed(f"{name} on item {item} was not set back")
            evidence["restored"] = now
        if expect.get("reconciled"):
            if self._drifted is None:
                raise StepFailed("nothing was drifted before the reconciliation")
            item, name, drifted = self._drifted
            found = [
                d
                for d in evidence.get("differences") or []
                if d.get("work_item_id") == item and d.get("field") == name
            ]
            now = self.board.service_board.get(item).fields.get(name)
            if not found or now == drifted:
                raise StepFailed(f"the reconciliation did not correct {name} on item {item}")
            evidence["corrected"] = {"item": item, "field": name, "value": now}
            evidence["differences"] = len(evidence["differences"])

    # -------------------------------------------------------------- expectations

    def _check(self, step: Step, run: RunRow | None) -> dict[str, Any]:
        expect = step.expect
        if run is None:
            raise StepFailed(f"no {step.terminal} run")
        run = self.service.get_run(run.run_id) or run
        if "run_number" in expect and run.run_number != int(expect["run_number"]):
            raise StepFailed(f"{run.run_id} is run {run.run_number}, not {expect['run_number']}")
        if "final_status" in expect and run.final_status != expect["final_status"]:
            raise StepFailed(
                f"{run.run_id} closed {run.final_status}, not {expect['final_status']}"
            )
        if "state" in expect and str(run.state) != expect["state"]:
            raise StepFailed(f"{run.run_id} is {run.state}, not {expect['state']}")
        evidence: dict[str, Any] = {}
        if expect.get("escalated"):
            self.drain()
            latest = self._latest(step)
            if latest is None or latest.state != RunState.ESCALATED:
                raise StepFailed(f"{step.terminal} did not escalate")
            evidence["escalated_run"] = latest.run_id
            evidence["trigger"] = latest.escalation_trigger
        if "arrow" in expect:
            self.drain()
            journey = DashboardService(self.runs).journey(run.usecase_id)
            arrows = [
                a
                for a in journey["arrows"]
                if a["from_run"] == run.run_id and a["kind"] == expect["arrow"]
            ]
            if not arrows:
                raise StepFailed(f"no {expect['arrow']} arrow from {run.run_id}")
            evidence["arrow"] = {k: arrows[0][k] for k in ("kind", "from_run", "to_run", "cause")}
        return evidence


def people_for(by_role: Mapping[str, Sequence[Actor]]) -> Callable[[str], Sequence[Actor]]:
    return lambda role: by_role[role]
