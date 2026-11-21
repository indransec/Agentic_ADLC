"""US2: deciding a run from the board (T029; FR-012..FR-016, FR-024, FR-028)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from adlc.engagement.model import ItemWrite
from tests.support.board import Rig
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, person


@pytest.fixture
def rig(h: Harness) -> Rig:
    return Rig(h)


def _needed(h: Harness, run_id: str) -> list[str]:
    run = h.run(run_id)
    with h.app.connect() as conn:
        ctx = h.orch.runs.context(conn, run)
    approved = {role for _, role in ctx.approvals}
    return sorted(ctx.required_plus_roles - approved) + sorted(ctx.rule_roles - approved)


def _save(
    rig: Rig, role: str, run_id: str, value: str, comment: str | None = None, **inputs: str
) -> None:
    fields: dict[str, Any] = {rig.mapping.decision_field: value}
    if comment is not None:
        fields[rig.mapping.comment_field] = comment
    for name, given in inputs.items():
        fields[rig.mapping.inputs()[name].field] = given
    rig.as_role(role).update(rig.item("run", run_id), ItemWrite(set=fields))


def _fields(rig: Rig, run_id: str) -> dict[str, Any]:
    return dict(rig.board.get(rig.item("run", run_id)).fields)


def test_pass_by_each_needed_approver_closes_the_run(rig: Rig, h: Harness) -> None:
    usecase, run_id = walk_to(h, "T1")
    rig.cycle()
    needed = _needed(h, run_id)
    assert needed
    for role in needed:
        _save(rig, role, run_id, rig.mapping.value_for("pass"), "looks right")
        rig.cycle()
        # the platform cleared the field for the next approver
        assert _fields(rig, run_id).get(rig.mapping.decision_field) in (None, "")
    assert h.run(run_id).final_status == "pass"
    epic = rig.board.get(rig.item("usecase", usecase))
    assert epic.fields[rig.mapping.field("usecase", "state")] == rig.mapping.column("T2")
    signers = {r[0] for r in h.sql("SELECT person FROM sign_off WHERE run_id = :r", r=run_id)}
    assert signers == {person(r).account_name for r in needed}
    details = [
        r[0] if isinstance(r[0], dict) else json.loads(r[0])
        for r in h.sql("SELECT detail FROM run_activity WHERE run_id = :r", r=run_id)
    ]
    assert sum(1 for d in details if "source" in d) == len(needed)
    assert all(o == ("accepted", None) for o in rig.outcomes())


def test_rework_inputs_from_fields_and_from_comment_lines(rig: Rig, h: Harness) -> None:
    _, run_id = walk_to(h, "T1")
    rig.cycle()
    role = _needed(h, run_id)[0]
    label = rig.mapping.inputs()["root_cause"].label
    reason = rig.mapping.inputs()["reason"].label
    _save(
        rig,
        role,
        run_id,
        rig.mapping.value_for("rework"),
        f"KPI missing\n{label}: requirement\n{reason}: gap",
    )
    rig.cycle()
    assert h.run(run_id).final_status == "rework"
    decision = h.sql("SELECT comment, root_cause FROM sign_off WHERE run_id = :r", r=run_id)[0]
    assert (decision[0], decision[1]) == ("KPI missing", "requirement")


def test_a_missing_input_is_refused_and_reverted(rig: Rig, h: Harness) -> None:
    _, run_id = walk_to(h, "T1")
    rig.cycle()
    role = _needed(h, run_id)[0]
    _save(rig, role, run_id, rig.mapping.value_for("rework"), "no cause given")
    rig.cycle()
    assert h.run(run_id).state == "awaiting_sign_off"
    assert _fields(rig, run_id).get(rig.mapping.decision_field) in (None, "")
    assert any(
        "refused" in c and rig.mapping.inputs()["root_cause"].label in c
        for c in rig.comments("run", run_id)
    )
    assert rig.outcomes()[-1] == ("refused", "missing_input")


def test_an_invalid_typed_value_is_refused_with_a_comment(rig: Rig, h: Harness) -> None:
    """Found in 018's live walk: a value the platform cannot store is refused like any invalid
    input (a comment, the decision cleared), never a failure that stalls the sync."""
    _, run_id = walk_to(h, "T0")
    rig.cycle()
    role = _needed(h, run_id)[0]
    _save(rig, role, run_id, rig.mapping.value_for("pass"), "ok", values="risk_tier: extreme")
    rig.cycle()
    assert h.run(run_id).state == "awaiting_sign_off"
    assert rig.outcomes()[-1][0] == "refused"
    assert any("risk_tier" in c for c in rig.comments("run", run_id))
    assert _fields(rig, run_id).get(rig.mapping.decision_field) in (None, "")
    _save(rig, role, run_id, rig.mapping.value_for("pass"), "ok", values="risk_tier: medium")
    rig.cycle()
    assert h.run(run_id).final_status == "pass"


def test_a_person_without_the_right_is_refused(rig: Rig, h: Harness) -> None:
    _, run_id = walk_to(h, "T1")
    rig.cycle()
    _save(rig, "sre", run_id, rig.mapping.value_for("pass"), "not mine")
    rig.cycle()
    assert h.run(run_id).state == "awaiting_sign_off"
    assert rig.outcomes()[-1] == ("refused", "not_authorised")
    assert _fields(rig, run_id).get(rig.mapping.decision_field) in (None, "")


def test_an_unknown_value_names_the_allowed_ones(rig: Rig, h: Harness) -> None:
    _, run_id = walk_to(h, "T1")
    rig.cycle()
    _save(rig, _needed(h, run_id)[0], run_id, "Maybe")
    rig.cycle()
    assert rig.outcomes()[-1] == ("refused", "unknown_value")
    assert any(rig.mapping.value_for("pass") in c for c in rig.comments("run", run_id))


def test_the_same_update_read_twice_has_one_effect(rig: Rig, h: Harness) -> None:
    _, run_id = walk_to(h, "T1")
    rig.cycle()
    role = _needed(h, run_id)[0]
    _save(rig, role, run_id, rig.mapping.value_for("pass"), "once")
    rig.sync.poll()
    with h.app.begin() as conn:  # an overlapping poll: the watermark moved back
        conn.exec_driver_sql("UPDATE board_sync_state SET watermark = '2000-01-01T00:00:00Z'")
    rig.sync.poll()
    rig.sync.recover()
    assert len(h.sql("SELECT 1 FROM sign_off WHERE run_id = :r", r=run_id)) == 1


def test_a_decision_on_a_run_decided_meanwhile_is_stale(rig: Rig, h: Harness) -> None:
    _, run_id = walk_to(h, "T1")
    rig.cycle()
    role = _needed(h, run_id)[0]
    _save(rig, role, run_id, rig.mapping.value_for("pass"), "late")
    h.pass_run(run_id)  # decided in the inbox before the poll
    rig.cycle()
    assert rig.outcomes()[-1][0] == "refused"
    assert rig.outcomes()[-1][1] in ("stale", "not_authorised")


def test_unmapped_user_is_refused(rig: Rig, h: Harness) -> None:
    _, run_id = walk_to(h, "T1")
    rig.cycle()
    stranger = rig.board.as_user("stranger@board.test")
    stranger.update(
        rig.item("run", run_id),
        ItemWrite(set={rig.mapping.decision_field: rig.mapping.value_for("pass")}),
    )
    rig.cycle()
    assert rig.outcomes()[-1] == ("refused", "not_mapped")
    assert h.run(run_id).state == "awaiting_sign_off"
    assert not any("product_owner" in c for c in rig.comments("run", run_id))
