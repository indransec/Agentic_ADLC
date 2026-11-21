"""SC-007: a lifecycle driven entirely from the board leaves the same platform records, in kind
and attribution, as the same decisions made through the inbox (T058)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Protocol

from adlc.engagement.model import ItemWrite
from adlc.orchestration import spec_view
from adlc.orchestration.interfaces import Clarification
from adlc.orchestration.stubs import StubAgent
from tests.support.board import Rig, board_pass, needed_roles
from tests.support.db import PlatformDatabase
from tests.support.orchestration import Harness, harness, person

ASK = Clarification(("Which channels?",))
T5_FIELDS = {
    "risk_acceptance": "accepted",
    "expiry": "2099-12-31",
    "compensating_control": "manual review",
}


class Driver(Protocol):
    h: Harness

    def submit(self, name: str) -> str: ...
    def pass_run(self, run_id: str, fields: dict[str, str] | None = None) -> None: ...
    def decide(self, role: str, run_id: str, decision: str, **inputs: Any) -> None: ...
    def answer(self, role: str, clarification_id: str, answers: list[str]) -> None: ...
    def waiver(self, role: str, run_id: str, approve: bool) -> None: ...
    def complete(self, role: str, run_id: str) -> None: ...


class Inbox:
    def __init__(self, h: Harness) -> None:
        self.h = h

    def submit(self, name: str) -> str:
        return self.h.submit(name)

    def pass_run(self, run_id: str, fields: dict[str, str] | None = None) -> None:
        self.h.pass_run(run_id, fields)

    def decide(self, role: str, run_id: str, decision: str, **inputs: Any) -> None:
        self.h.service.decide(person(role), run_id, decision, **inputs)
        self.h.drain()

    def answer(self, role: str, clarification_id: str, answers: list[str]) -> None:
        self.h.service.answer_clarification(person(role), clarification_id, answers)
        self.h.drain()

    def waiver(self, role: str, run_id: str, approve: bool) -> None:
        self.h.service.decide_waiver(person(role), self.h.run(run_id).pending_waiver_id, approve)
        self.h.drain()

    def complete(self, role: str, run_id: str) -> None:
        self.h.service.complete_escalation(person(role), run_id, {})
        self.h.drain()


class Board:
    def __init__(self, h: Harness) -> None:
        self.h = h
        self.rig = Rig(h)
        self.m = self.rig.mapping

    def _save(self, role: str, kind: str, object_id: str, fields: dict[str, Any]) -> None:
        self.rig.cycle()
        self.rig.as_role(role).update(self.rig.item(kind, object_id), ItemWrite(set=fields))
        self.rig.cycle()

    def submit(self, name: str) -> str:
        f = self.m.item("usecase").fields
        self.rig.as_role("business_owner").create(
            self.m.item("usecase").type,
            {f["title"]: name, f["description"]: "x" * 250, f["area"]: self.m.area},
        )
        self.rig.cycle()
        return str(self.h.sql("SELECT usecase_id FROM usecase WHERE name = :n", n=name)[0][0])

    def pass_run(self, run_id: str, fields: dict[str, str] | None = None) -> None:
        self.rig.cycle()
        board_pass(self.rig, run_id, fields)

    def decide(self, role: str, run_id: str, decision: str, **inputs: Any) -> None:
        values = {self.m.decision_field: self.m.value_for(decision)}
        if inputs.get("comment"):
            values[self.m.comment_field] = inputs["comment"]
        for name in ("root_cause", "reason", "target_terminal"):
            if inputs.get(name):
                values[self.m.inputs()[name].field] = inputs[name]
        if inputs.get("fields"):
            values[self.m.inputs()["values"].field] = "\n".join(
                f"{k}: {v}" for k, v in inputs["fields"].items()
            )
        self._save(role, "run", run_id, values)

    def answer(self, role: str, clarification_id: str, answers: list[str]) -> None:
        text = (
            answers[0]
            if len(answers) == 1
            else "\n".join(f"{i}. {a}" for i, a in enumerate(answers, 1))
        )
        self._save(
            role, "clarification", clarification_id, {self.m.field("clarification", "answer"): text}
        )

    def waiver(self, role: str, run_id: str, approve: bool) -> None:
        value = self.m.value_for("approve_waiver" if approve else "reject_waiver")
        self._save(role, "run", run_id, {self.m.decision_field: value})

    def complete(self, role: str, run_id: str) -> None:
        self._save(
            role, "run", run_id, {self.m.decision_field: self.m.value_for("complete_escalation")}
        )


def _lifecycle(d: Driver) -> None:
    h = d.h
    a = d.submit("Case A")
    d.pass_run(h.active(a, "T0").run_id, {"risk_tier": "medium"})
    t1 = h.active(a, "T1").run_id
    d.decide(
        needed_roles(h, t1)[0],
        t1,
        "rework",
        comment="KPI missing",
        root_cause="requirement",
        reason="gap",
    )
    d.pass_run(h.active(a, "T1").run_id)
    t2 = h.active(a, "T2").run_id
    d.answer("engineering_lead", f"{t2}/clar-1", ["Web and email"])
    d.pass_run(h.active(a, "T2").run_id)
    for terminal in ("T3", "T4"):
        d.pass_run(h.active(a, terminal).run_id)
    t5 = h.active(a, "T5").run_id
    d.decide("security_officer", t5, "exception", reason="known gap", fields=T5_FIELDS)
    d.waiver("risk_owner", t5, True)
    b = d.submit("Case B")
    d.pass_run(h.active(b, "T0").run_id, {"risk_tier": "medium"})
    b1 = h.active(b, "T1").run_id
    h.clock.advance(timedelta(days=10, seconds=1))  # T1 escalate_after
    h.drain()
    run = h.run(b1)
    accountable = sorted(
        spec_view.accountable_roles(h.orch.runs.entry(run.terminal_id, run.spec_version).spec)
    )[0]
    d.complete(accountable, b1)
    d.decide(needed_roles(h, b1)[0], b1, "terminate", reason="duplicate")


def _records(h: Harness) -> dict[str, Any]:
    return {
        "runs": sorted(
            (str(r[0]), str(r[1]), r[2])
            for r in h.sql("SELECT run_id, state, final_status FROM terminal_run")
        ),
        "sign_offs": sorted(
            (str(r[0]), str(r[1]), str(r[2]), str(r[3]), r[4])
            for r in h.sql("SELECT run_id, role, person, decision, root_cause FROM sign_off")
        ),
        "ledger": sorted(
            str(r[0]) for r in h.sql("SELECT run_id FROM ledger_record WHERE run_id IS NOT NULL")
        ),
        "waivers": [tuple(r) for r in h.sql("SELECT status, proposed_by, decided_by FROM waiver")],
        "answers": [
            tuple(r)
            for r in h.sql("SELECT clarification_id, answered_by FROM clarification_answer")
        ],
        "usecases": sorted(
            tuple(r) for r in h.sql("SELECT usecase_id, status, submitted_by FROM usecase")
        ),
    }


def test_the_board_and_the_inbox_leave_the_same_records(orch_template: PlatformDatabase) -> None:
    results = {}
    for name, driver in (("inbox", Inbox), ("board", Board)):
        with harness(orch_template, agent=StubAgent({"T2": {1: ASK}})) as h:
            _lifecycle(driver(h))
            results[name] = _records(h)
    assert results["board"] == results["inbox"]
    assert results["board"]["waivers"] and results["board"]["answers"]
    assert any(status == "rework" for _, _, status in results["board"]["runs"])
