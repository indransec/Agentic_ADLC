"""The demo driver (feature 014, research R-01 to R-03): runs a demo script on the platform.

For each step it waits until the step's terminal has a run that needs people, takes the step's
actions (``auto``) or tells the presenter what to do and waits until it is done, then checks the
step's expectation. Human actions go through the platform's service operations as the named roles
(the replayer's operations: every needed approver passes, an exception's waiver is approved by
another person, a clarification is answered by its addressed role). Faults are asked of the host
wrapper (operator access to the pilot); the monitors are evaluated after one. Nothing here names a
terminal or a use case: they come from the script and the reference.
"""

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import text

from adlc.agents.replay import Reference, Replayer
from adlc.dashboard.service import DashboardService
from adlc.demo.script import MOMENTS, Action, DemoScript, Step
from adlc.inbox.changes import ChangeService
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
    ) -> None:
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

    # -------------------------------------------------------------- driving

    def run(self, from_step: int = 1) -> DemoReport:
        report = DemoReport([], self.usecases)
        self._resume()
        for step in self.script.steps:
            if step.number < from_step:
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
                        "SELECT usecase_id FROM run.usecase WHERE name = :n "
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
                if self.auto:
                    self._act(run, action)
                else:
                    self._presenter(run, action)
            except StepFailed:
                raise
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
