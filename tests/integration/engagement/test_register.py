"""US3: registering a use case from the board (T034; FR-018)."""

from __future__ import annotations

import pytest

from adlc.engagement.model import ItemWrite
from tests.support.board import Rig
from tests.support.orchestration import Harness

SUBMITTER = "business_owner"  # an accountable role of the terminal a submission opens


@pytest.fixture
def rig(h: Harness) -> Rig:
    return Rig(h)


def _epic(rig: Rig, role: str, title: str, description: str, area: str | None = None) -> int:
    f = rig.mapping.item("usecase").fields
    fields = {f["title"]: title, f["description"]: description, f["area"]: area or rig.mapping.area}
    return rig.as_role(role).create(rig.mapping.item("usecase").type, fields).id


def _usecases(h: Harness) -> list[tuple[str, str, str]]:
    return [(r[0], r[1], r[2]) for r in h.sql("SELECT usecase_id, name, submitted_by FROM usecase")]


def test_an_epic_becomes_a_use_case(rig: Rig, h: Harness) -> None:
    item = _epic(rig, SUBMITTER, "Claims triage", "<p>Triage claims &amp; fraud</p>")
    rig.cycle()
    [(usecase, name, by)] = _usecases(h)
    assert (name, by) == ("Claims triage", f"{SUBMITTER}-person")
    intake = h.sql("SELECT intake_text FROM usecase")[0][0]
    assert intake == "Triage claims & fraud"
    epic = rig.board.get(item)
    assert epic.fields[rig.mapping.field("usecase", "usecase_id")] == usecase
    first = h.runs(usecase)[0].terminal_id
    assert epic.fields[rig.mapping.field("usecase", "state")] == rig.mapping.column(first)
    assert any(usecase in c for c in rig.comments("usecase", usecase))


def test_registered_once(rig: Rig, h: Harness) -> None:
    item = _epic(rig, SUBMITTER, "Once", "intake")
    rig.cycle()
    rig.as_role(SUBMITTER).update(
        item, ItemWrite(set={rig.mapping.field("usecase", "title"): "Once more"})
    )
    rig.cycle()
    assert len(_usecases(h)) == 1


def test_a_column_chosen_by_the_person_is_not_used(rig: Rig, h: Harness) -> None:
    f = rig.mapping.item("usecase").fields
    fields = {
        f["title"]: "Jumps ahead",
        f["description"]: "intake",
        f["area"]: rig.mapping.area,
        f["state"]: rig.mapping.column("T5"),
    }
    item = rig.as_role(SUBMITTER).create(rig.mapping.item("usecase").type, fields).id
    rig.cycle()
    [(usecase, _, _)] = _usecases(h)
    first = h.runs(usecase)[0].terminal_id
    assert rig.board.get(item).fields[f["state"]] == rig.mapping.column(first)


def test_an_empty_description_then_an_edit(rig: Rig, h: Harness) -> None:
    item = _epic(rig, SUBMITTER, "No intake", "")
    rig.cycle()
    assert _usecases(h) == []
    assert rig.outcomes()[-1] == ("refused", "invalid_usecase")
    assert any("description" in text for _, text in rig.board.comments(item))
    rig.as_role(SUBMITTER).update(
        item, ItemWrite(set={rig.mapping.field("usecase", "description"): "Now with intake"})
    )
    rig.cycle()
    assert [n for _, n, _ in _usecases(h)] == ["No intake"]


def test_an_unmapped_user_or_a_role_that_may_not_submit(rig: Rig, h: Harness) -> None:
    f = rig.mapping.item("usecase").fields
    stranger = rig.board.as_user("stranger@board.test")
    stranger.create(
        rig.mapping.item("usecase").type,
        {f["title"]: "x", f["description"]: "y", f["area"]: rig.mapping.area},
    )
    _epic(rig, "sre", "Not mine", "intake")
    rig.cycle()
    assert _usecases(h) == []
    assert sorted(str(code) for _, code in rig.outcomes()) == ["not_authorised", "not_mapped"]


def test_projected_epics_and_other_areas_are_never_registered(rig: Rig, h: Harness) -> None:
    h.submit("From the inbox")
    _epic(rig, SUBMITTER, "Elsewhere", "intake", area="Other area")
    rig.cycle()
    assert [n for _, n, _ in _usecases(h)] == ["From the inbox"]
