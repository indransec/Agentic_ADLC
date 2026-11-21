"""SC-004: every refusal reason reverts the request with a comment naming the reason and changes
nothing in the platform (T055). (``already_answered`` is covered in test_answer.py.)"""

from __future__ import annotations

from adlc.engagement.model import ItemWrite
from tests.support.board import Rig, needed_roles
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness

DECISION_TABLES = ("usecase", "sign_off", "waiver", "clarification_answer", "run_transition")


def _counts(h: Harness) -> dict[str, int]:
    return {t: h.sql(f"SELECT count(*) FROM {t}")[0][0] for t in DECISION_TABLES}  # noqa: S608


def test_every_refusal_is_reverted_and_changes_nothing(h: Harness) -> None:
    rig = Rig(h)
    usecase, run_id = walk_to(h, "T1")
    closed_case, closed_run = walk_to(h, "T1")
    role = needed_roles(h, closed_run)[0]
    h.service.decide(
        __import__("tests.support.orchestration", fromlist=["person"]).person(role),
        closed_run,
        "terminate",
        reason="r",
    )
    h.drain()
    rig.cycle()
    run_item = rig.item("run", run_id)
    approver = needed_roles(h, run_id)[0]
    d = rig.mapping.decision_field
    pass_value = rig.mapping.value_for("pass")
    f = rig.mapping.item("usecase").fields
    before = _counts(h)
    rig.board.as_user("stranger@board.test").update(
        run_item, ItemWrite(set={d: pass_value})
    )  # not_mapped
    rig.sync.poll()  # each refusal is seen before the next try
    rig.as_role("sre").update(run_item, ItemWrite(set={d: pass_value}))  # not_authorised
    rig.sync.poll()  # each refusal is seen before the next try
    rig.as_role(approver).update(
        run_item, ItemWrite(set={d: rig.mapping.value_for("rework")})
    )  # missing_input
    rig.sync.poll()  # each refusal is seen before the next try
    rig.as_role(approver).update(
        run_item,
        ItemWrite(
            set={
                d: rig.mapping.value_for("rework"),
                rig.mapping.comment_field: "c",
                rig.mapping.inputs()["root_cause"].field: "nonsense",
            }
        ),
    )  # invalid_input
    rig.sync.poll()
    rig.sync.poll()  # each refusal is seen before the next try
    rig.as_role(approver).update(run_item, ItemWrite(set={d: "Perhaps"}))  # unknown_value
    rig.sync.poll()  # each refusal is seen before the next try
    rig.as_role(approver).update(
        rig.item("usecase", usecase), ItemWrite(set={f["state"]: rig.mapping.column("T9")})
    )  # platform_field
    rig.sync.poll()  # each refusal is seen before the next try
    rig.as_role("business_owner").create(
        rig.mapping.item("usecase").type,
        {f["title"]: "x", f["description"]: "", f["area"]: rig.mapping.area},
    )  # invalid_usecase
    rig.sync.poll()
    rig.sync.poll()  # each refusal is seen before the next try
    rig.as_role(role).update(rig.item("run", closed_run), ItemWrite(set={d: pass_value}))  # closed
    rig.sync.poll()
    codes = {code for outcome, code in rig.outcomes() if outcome == "refused"}
    assert codes >= {
        "not_mapped",
        "not_authorised",
        "missing_input",
        "invalid_input",
        "unknown_value",
        "platform_field",
        "invalid_usecase",
        "closed",
    }
    assert _counts(h) == before
    assert rig.board.get(run_item).fields.get(d) in (None, "")
    for item in rig.board.item_ids():
        for author, text in rig.board.comments(item):
            if "refused" in text:
                assert author == rig.identities.service_identity and "—" in text
    reverted = h.sql("SELECT count(*) FROM inbound_outcome WHERE outcome = 'refused' AND reverted")[
        0
    ][0]
    assert reverted >= 6  # every request field cleared (registration is left for an edit)
