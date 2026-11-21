"""The desired board state of a use case (T021, FR-005, FR-006; research R-03, R-13)."""

from dataclasses import replace
from pathlib import Path

import pytest

from adlc.engagement.desired import (
    ChangeSnapshot,
    ClarificationSnapshot,
    RunSnapshot,
    UseCaseSnapshot,
    desired,
)
from adlc.engagement.mapping import TrackerMapping

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = "http://ui.test/run?id="


@pytest.fixture
def mapping() -> TrackerMapping:
    return TrackerMapping.load(ROOT / "adlc-specs" / "tracker_mapping.yaml")


FORM = {
    "outcomes": ["pass", "rework", "exception", "terminate"],
    "requires": {"rework": ["comment", "root_cause"], "terminate": ["reason"]},
    "root_causes": ["requirement", "qualification"],
    "target_terminal_for": ["qualification"],
    "target_terminals": ["T0", "T1"],
    "typed_fields": ["risk_tier"],
    "reason_required_unless": "pass",
}


def _run(state: str = "awaiting_sign_off", **changes: object) -> RunSnapshot:
    base = RunSnapshot(
        run_id="UC-0001/T1/run-1",
        terminal_id="T1",
        run_number=1,
        state=state,
        final_status=None,
        form=FORM if state == "awaiting_sign_off" else None,
        recommendation={"status": "pass", "summary": "Looks complete"},
        approvals=(),
        waiting_roles=("product_owner",),
        waiver=None,
        clarifications=(),
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def _usecase(*runs: RunSnapshot, status: str = "active") -> UseCaseSnapshot:
    return UseCaseSnapshot("UC-0001", "Claims triage", "Triage <claims> fast", status, runs)


def _by_kind(items: list) -> dict[str, list]:  # type: ignore[type-arg]
    found: dict[str, list] = {}  # type: ignore[type-arg]
    for item in items:
        found.setdefault(item.kind, []).append(item)
    return found


def test_a_use_case_with_no_runs(mapping: TrackerMapping) -> None:
    items = desired(_usecase(), mapping, EVIDENCE)
    assert [i.kind for i in items] == ["usecase"]
    epic = items[0]
    assert epic.item_type == mapping.item("usecase").type
    assert epic.fields[mapping.field("usecase", "usecase_id")] == "UC-0001"
    first = next(iter(mapping._data["items"]["usecase"]["columns"]))  # noqa: SLF001
    assert epic.fields[mapping.field("usecase", "state")] == mapping.column(first)
    assert epic.create_fields[mapping.field("usecase", "title")] == "Claims triage"
    assert "&lt;claims&gt;" in epic.create_fields[mapping.field("usecase", "description")]
    assert epic.create_fields[mapping.field("usecase", "area")] == mapping.area
    assert epic.parent is None


def test_a_run_awaiting_sign_off(mapping: TrackerMapping) -> None:
    items = _by_kind(desired(_usecase(_run()), mapping, EVIDENCE))
    epic, run = items["usecase"][0], items["run"][0]
    assert epic.fields[mapping.field("usecase", "state")] == mapping.column("T1")
    assert epic.fields[mapping.field("usecase", "sub_stage")] == mapping.sub_stage(
        "awaiting_sign_off"
    )
    assert run.parent == ("usecase", "UC-0001")
    assert run.fields[mapping.field("run", "run_id")] == "UC-0001/T1/run-1"
    assert run.fields[mapping.field("run", "evidence")] == EVIDENCE + "UC-0001%2FT1%2Frun-1"
    assert run.fields[mapping.field("run", "state")] == mapping.run_item_state("awaiting_sign_off")
    description = run.fields[mapping.field("run", "description")]
    for text in (
        *(mapping.value_for(o) for o in FORM["outcomes"]),
        "requirement",
        "qualification",
        "risk_tier",
        "Looks complete",
        mapping.inputs()["root_cause"].label,
        "product_owner",
    ):
        assert text in description, text


def test_approvals_change_the_run_item(mapping: TrackerMapping) -> None:
    before = _by_kind(desired(_usecase(_run()), mapping, EVIDENCE))["run"][0]
    after = _by_kind(
        desired(
            _usecase(
                _run(approvals=(("Ann", "product_owner"),), waiting_roles=("business_owner",))
            ),
            mapping,
            EVIDENCE,
        )
    )["run"][0]
    assert before.hash != after.hash
    assert "Ann" in after.fields[mapping.field("run", "description")]


def test_a_pending_waiver_and_escalation(mapping: TrackerMapping) -> None:
    waiver = {"waiver_id": "WVR-0001", "status": "proposed", "approver_roles": ["risk_owner"]}
    run = _by_kind(desired(_usecase(_run(waiver=waiver)), mapping, EVIDENCE))["run"][0]
    text = run.fields[mapping.field("run", "description")]
    assert (
        "WVR-0001" in text and mapping.value_for("approve_waiver") in text and "risk_owner" in text
    )
    escalated = _by_kind(desired(_usecase(_run("escalated", form=None)), mapping, EVIDENCE))["run"][
        0
    ]
    assert (
        mapping.value_for("complete_escalation")
        in escalated.fields[mapping.field("run", "description")]
    )


def test_a_closed_run_and_the_next_terminal(mapping: TrackerMapping) -> None:
    closed = _run("closed", final_status="pass", form=None)
    nxt = _run(
        "building",
        run_id="UC-0001/T2/run-1",
        terminal_id="T2",
        form=None,
    )
    items = _by_kind(desired(_usecase(closed, nxt), mapping, EVIDENCE))
    epic = items["usecase"][0]
    assert epic.fields[mapping.field("usecase", "state")] == mapping.column("T2")
    assert epic.fields[mapping.field("usecase", "sub_stage")] == mapping.sub_stage("building")
    states = {r.object_id: r.fields[mapping.field("run", "state")] for r in items["run"]}
    assert states["UC-0001/T1/run-1"] == mapping.run_item_state("closed")


def test_a_terminated_use_case(mapping: TrackerMapping) -> None:
    run = _run("closed", final_status="terminate", form=None)
    items = _by_kind(desired(_usecase(run, status="terminated"), mapping, EVIDENCE))
    assert items["usecase"][0].fields[
        mapping.field("usecase", "state")
    ] == mapping.terminated_state("usecase")
    assert items["run"][0].fields[mapping.field("run", "state")] == mapping.terminated_state("run")


def test_a_completed_use_case(mapping: TrackerMapping) -> None:
    run = _run("closed", final_status="pass", form=None)
    items = desired(_usecase(run, status="closed"), mapping, EVIDENCE)
    assert items[0].fields[mapping.field("usecase", "state")] == mapping.closed_column


def test_clarification_open_and_answered(mapping: TrackerMapping) -> None:
    open_round = ClarificationSnapshot(
        "UC-0001/T1/run-1/clar-1", "product_owner", ("Which KPI?", "Which region?"), None
    )
    run = _run("awaiting_clarification", form=None, clarifications=(open_round,))
    task = _by_kind(desired(_usecase(run), mapping, EVIDENCE))["clarification"][0]
    assert task.parent == ("run", "UC-0001/T1/run-1")
    assert task.fields[mapping.field("clarification", "state")] == mapping.clarification_open
    text = task.fields[mapping.field("clarification", "description")]
    assert "1. Which KPI?" in text and "2. Which region?" in text and "product_owner" in text
    answered = replace(open_round, answered_by="owner.product")
    run2 = _run("building", form=None, clarifications=(answered,))
    task2 = _by_kind(desired(_usecase(run2), mapping, EVIDENCE))["clarification"][0]
    assert task2.fields[mapping.field("clarification", "state")] == mapping.clarification_answered
    assert task.hash != task2.hash


def test_hash_is_stable_and_order_free(mapping: TrackerMapping) -> None:
    first = desired(_usecase(_run()), mapping, EVIDENCE)
    second = desired(_usecase(_run()), mapping, EVIDENCE)
    assert [i.hash for i in first] == [i.hash for i in second]


def test_only_platform_written_fields_are_compared(mapping: TrackerMapping) -> None:
    for item in desired(_usecase(_run()), mapping, EVIDENCE):
        assert set(item.fields) <= mapping.platform_written(item.kind)
        assert not set(item.fields) & mapping.person_input_fields(item.kind)


# ------------------------------------------------------------------ 020 change requests


def _change(state: str = "new", **changes: object) -> ChangeSnapshot:
    base = ChangeSnapshot(
        change_id="CHG-0001",
        state=state,
        summary="Release <it-triage> 1.0",
        risk="low",
        window="2026-11-21T10:00 to 2026-11-21T12:00",
        approver_role="release_manager",
        decided_by=None,
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def test_a_change_request_is_an_item_under_its_run(mapping: TrackerMapping) -> None:
    run = _run(changes=(_change(),))
    found = _by_kind(desired(_usecase(run), mapping, EVIDENCE))
    (item,) = found["change"]
    f = mapping.item("change").fields
    assert item.parent == ("run", run.run_id)
    assert item.object_id == "CHG-0001"
    assert item.item_type == mapping.item("change").type
    assert item.fields[f["state"]] == mapping.change_state("awaiting")
    assert item.fields[f["change_id"]] == "CHG-0001"
    assert "CHG-0001" in item.fields[f["title"]] and "T1 run 1" in item.fields[f["title"]]
    description = item.fields[f["description"]]
    assert "Release &lt;it-triage&gt; 1.0" in description  # escaped
    assert "release_manager" in description and "low" in description
    assert mapping.value_for("approve_change") in description
    assert mapping.value_for("reject_change") in description


@pytest.mark.parametrize(
    ("state", "status"), [("new", "awaiting"), ("approved", "approved"), ("rejected", "rejected")]
)
def test_a_change_item_follows_the_record(mapping: TrackerMapping, state: str, status: str) -> None:
    decided = None if state == "new" else "release_manager-person"
    run = _run(changes=(_change(state, decided_by=decided),))
    (item,) = _by_kind(desired(_usecase(run), mapping, EVIDENCE))["change"]
    assert item.fields[mapping.field("change", "state")] == mapping.change_state(status)
    if decided:
        assert "release_manager-person" in item.fields[mapping.field("change", "description")]


def test_every_change_of_a_run_has_an_item(mapping: TrackerMapping) -> None:
    run = _run(changes=(_change(), _change("approved", change_id="CHG-0002", decided_by="x")))
    found = _by_kind(desired(_usecase(run), mapping, EVIDENCE))
    assert [i.object_id for i in found["change"]] == ["CHG-0001", "CHG-0002"]
