"""How a board update is read (T026; contracts/inbound-rules.md §1-§2; research R-05)."""

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from adlc.engagement.classify import Action, classify
from adlc.engagement.mapping import TrackerMapping
from adlc.engagement.model import BoardUpdate, FieldChange
from adlc.engagement.store import Link

ROOT = Path(__file__).resolve().parents[3]
MAPPING = TrackerMapping.load(ROOT / "adlc-specs" / "tracker_mapping.yaml")
PERSON = "person@board.test"
SERVICE = "service@board.test"
EPIC = MAPPING.item("usecase").type
RUN = MAPPING.item("run").type
TASK = MAPPING.item("clarification").type


def _link(kind: str, object_id: str = "UC-0001") -> Link:
    return Link(kind, object_id, 5, MAPPING.item(kind).type, "h", 2, 0)


def _update(
    fields: dict[str, tuple[object, object]], update_id: int = 2, by: str = PERSON
) -> BoardUpdate:
    return BoardUpdate(5, update_id, update_id, by, {k: FieldChange(*v) for k, v in fields.items()})


def _kinds(actions: list[Action]) -> list[str]:
    return [a.kind for a in actions]


def test_own_updates() -> None:
    update = _update({MAPPING.decision_field: (None, "Pass")}, by=SERVICE)
    assert _kinds(classify(update, RUN, _link("run"), None, MAPPING, SERVICE)) == ["own"]


def test_a_decision_on_a_run_item() -> None:
    update = _update({MAPPING.decision_field: (None, "Pass")})
    [action] = classify(update, RUN, _link("run"), None, MAPPING, SERVICE)
    assert action.kind == "decide" and action.value == "Pass"


def test_a_cleared_decision_is_ignored() -> None:
    update = _update({MAPPING.decision_field: ("Pass", None)})
    assert _kinds(classify(update, RUN, _link("run"), None, MAPPING, SERVICE)) == ["ignored"]


def test_a_platform_field_and_a_decision_in_one_update() -> None:
    state = MAPPING.field("run", "state")
    update = _update({MAPPING.decision_field: (None, "Pass"), state: ("Active", "Closed")})
    actions = classify(update, RUN, _link("run"), None, MAPPING, SERVICE)
    assert _kinds(actions) == ["revert", "decide"]
    assert actions[0].fields == (state,)


def test_the_epic_column_moved_by_a_person() -> None:
    state = MAPPING.field("usecase", "state")
    update = _update({state: ("a", "b")})
    actions = classify(update, EPIC, _link("usecase"), None, MAPPING, SERVICE)
    assert _kinds(actions) == ["revert"] and actions[0].fields == (state,)


def test_unread_fields_are_ignored() -> None:
    update = _update({"System.Tags": (None, "x")})
    assert _kinds(classify(update, RUN, _link("run"), None, MAPPING, SERVICE)) == ["ignored"]


def test_an_answer_on_a_clarification_item() -> None:
    answer = MAPPING.field("clarification", "answer")
    update = _update({answer: (None, "1. Yes")})
    [action] = classify(
        update, TASK, _link("clarification", "UC-0001/T1/run-1/clar-1"), None, MAPPING, SERVICE
    )
    assert action.kind == "answer" and action.value == "1. Yes"


@pytest.mark.parametrize("update_id", [1, 3])
def test_registration_of_a_new_or_edited_epic(update_id: int) -> None:
    title = MAPPING.field("usecase", "title")
    update = _update({title: (None, "New case")}, update_id)
    [action] = classify(update, EPIC, None, MAPPING.area, MAPPING, SERVICE)
    assert action.kind == "register_usecase"


def test_an_epic_outside_the_area_is_ignored() -> None:
    title = MAPPING.field("usecase", "title")
    update = _update({title: (None, "New case")}, 1)
    assert _kinds(classify(update, EPIC, None, "Elsewhere", MAPPING, SERVICE)) == ["ignored"]


def test_an_unlinked_item_of_another_type_is_ignored() -> None:
    update = _update({MAPPING.decision_field: (None, "Pass")}, 1)
    assert _kinds(classify(update, RUN, None, MAPPING.area, MAPPING, SERVICE)) == ["ignored"]


def test_a_link_side_update_is_ignored() -> None:
    update = BoardUpdate(5, 4, 3, PERSON)
    assert _kinds(classify(update, EPIC, _link("usecase"), None, MAPPING, SERVICE)) == ["ignored"]


FIELD_NAMES = st.sampled_from(
    sorted(
        {MAPPING.decision_field, "System.Tags", MAPPING.field("run", "state")}
        | MAPPING.platform_written("usecase")
    )
)


@given(
    st.dictionaries(FIELD_NAMES, st.one_of(st.none(), st.text(max_size=5)), max_size=4),
    st.sampled_from([EPIC, RUN, TASK, "Bug"]),
    st.sampled_from(["usecase", "run", "clarification", None]),
    st.sampled_from([PERSON, SERVICE]),
)
def test_classify_is_total_and_deterministic(
    changes: dict[str, object], item_type: str, kind: str | None, by: str
) -> None:
    update = BoardUpdate(5, 2, 2, by, {k: FieldChange(None, v) for k, v in changes.items()})
    link = None if kind is None else _link(kind)
    first = classify(update, item_type, link, MAPPING.area, MAPPING, SERVICE)
    assert first == classify(update, item_type, link, MAPPING.area, MAPPING, SERVICE)
    assert first and all(
        a.kind in {"own", "register_usecase", "decide", "answer", "revert", "ignored"}
        for a in first
    )
