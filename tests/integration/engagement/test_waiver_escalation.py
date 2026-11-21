"""US5: waivers, escalations and termination from the board (T039)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from adlc.engagement.model import ItemWrite
from adlc.orchestration import spec_view
from adlc.orchestration.service import Actor, NotAuthorised
from tests.support.board import Rig
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, person

DUAL = "dual@board.test"  # holds the proposer's and the approver's role
DUAL_ACCOUNT = "dual-person"
DUAL_ROLES = frozenset({"security_officer", "risk_owner"})
T5_VALUES = "risk_acceptance: accepted\nexpiry: 2099-12-31\ncompensating_control: manual review"


@pytest.fixture
def rig(h: Harness) -> Rig:
    return Rig(h, extra={DUAL: (DUAL_ACCOUNT, DUAL_ROLES)})


def _save(rig: Rig, who: Any, run_id: str, value: str, **fields: str) -> None:
    board = rig.board.as_user(who) if "@" in who else rig.as_role(who)
    values = {rig.mapping.decision_field: value}
    for name, given in fields.items():
        key = rig.mapping.comment_field if name == "comment" else rig.mapping.inputs()[name].field
        values[key] = given
    board.update(rig.item("run", run_id), ItemWrite(set=values))


def _propose(rig: Rig, who: str, run_id: str) -> None:
    _save(
        rig, who, run_id, rig.mapping.value_for("exception"), reason="known gap", values=T5_VALUES
    )
    rig.cycle()


def test_exception_then_approval_on_the_board(rig: Rig, h: Harness) -> None:
    usecase, run_id = walk_to(h, "T5")
    rig.cycle()
    _propose(rig, "security_officer", run_id)
    assert h.run(run_id).pending_waiver_id == "WVR-0001"
    text = rig.board.get(rig.item("run", run_id)).fields[rig.mapping.field("run", "description")]
    assert "WVR-0001" in text and "risk_owner" in text
    _save(rig, "risk_owner", run_id, rig.mapping.value_for("approve_waiver"), comment="one quarter")
    rig.cycle()
    assert h.run(run_id).final_status == "exception"
    assert tuple(h.sql("SELECT status, decided_by FROM waiver")[0]) == (
        "approved",
        "risk_owner-person",
    )
    assert h.active(usecase, "T6")


def test_rejection_on_the_board(rig: Rig, h: Harness) -> None:
    _, run_id = walk_to(h, "T5")
    rig.cycle()
    _propose(rig, "security_officer", run_id)
    _save(rig, "risk_owner", run_id, rig.mapping.value_for("reject_waiver"), comment="no")
    rig.cycle()
    assert h.sql("SELECT status FROM waiver")[0][0] == "rejected"


def test_the_proposer_never_approves_board_and_board(rig: Rig, h: Harness) -> None:
    _, run_id = walk_to(h, "T5")
    rig.cycle()
    _propose(rig, DUAL, run_id)
    _save(rig, DUAL, run_id, rig.mapping.value_for("approve_waiver"))
    rig.cycle()
    assert rig.outcomes()[-1] == ("refused", "not_authorised")
    assert h.sql("SELECT status FROM waiver")[0][0] == "proposed"


def test_the_proposer_never_approves_inbox_and_board(rig: Rig, h: Harness) -> None:
    _, run_id = walk_to(h, "T5")
    rig.cycle()
    dual = Actor(DUAL_ACCOUNT, DUAL_ROLES)
    fields = dict(line.split(": ", 1) for line in T5_VALUES.splitlines())
    h.service.decide(dual, run_id, "exception", reason="r", fields=fields)
    rig.cycle()
    _save(rig, DUAL, run_id, rig.mapping.value_for("approve_waiver"))
    rig.cycle()
    assert rig.outcomes()[-1] == ("refused", "not_authorised")


def test_the_proposer_never_approves_board_and_inbox(rig: Rig, h: Harness) -> None:
    _, run_id = walk_to(h, "T5")
    rig.cycle()
    _propose(rig, DUAL, run_id)
    with pytest.raises(NotAuthorised):
        h.service.decide_waiver(Actor(DUAL_ACCOUNT, DUAL_ROLES), "WVR-0001", True)


def test_complete_an_escalation(rig: Rig, h: Harness) -> None:
    _, run_id = walk_to(h, "T1")
    h.clock.advance(timedelta(days=10, seconds=1))  # T1 escalate_after
    h.drain()
    rig.cycle()
    assert h.run(run_id).state == "escalated"
    run = h.run(run_id)
    spec = h.orch.runs.entry(run.terminal_id, run.spec_version).spec
    accountable = sorted(spec_view.accountable_roles(spec))[0]
    _save(rig, accountable, run_id, rig.mapping.value_for("complete_escalation"))
    rig.cycle()
    assert h.run(run_id).state == "awaiting_sign_off"


def test_terminate_with_and_without_a_reason(rig: Rig, h: Harness) -> None:
    usecase, run_id = walk_to(h, "T1")
    rig.cycle()
    run = h.run(run_id)
    with h.app.connect() as conn:
        role = sorted(h.orch.runs.context(conn, run).rule_roles)[0]
    _save(rig, role, run_id, rig.mapping.value_for("terminate"))
    rig.cycle()
    assert rig.outcomes()[-1] == ("refused", "missing_input")
    _save(rig, role, run_id, rig.mapping.value_for("terminate"), reason="duplicate of another case")
    rig.cycle()
    assert h.sql("SELECT status FROM usecase")[0][0] == "terminated"
    epic = rig.board.get(rig.item("usecase", usecase))
    assert epic.fields[rig.mapping.field("usecase", "state")] == rig.mapping.terminated_state(
        "usecase"
    )
    assert person(role)
