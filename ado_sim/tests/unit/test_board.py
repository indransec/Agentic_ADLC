"""017 T018: board columns and cards (FR-005, FR-006, FR-009; research R-06)."""

from __future__ import annotations

from ado_sim.db import Database
from ado_sim.pages.board import columns
from ado_sim.workitems import WorkItemStore
from tests.conftest import People, add, title

AREA = "Agentic ADLC\\Use cases"
SUB = "Custom.AdlcSubStage"


def _epic(store: WorkItemStore, people: People, name: str, *extra: dict[str, object]) -> int:
    return store.create("Epic", [title(name), *extra], people.service).id


def test_columns_in_the_process_order(db: Database, store: WorkItemStore, people: People) -> None:
    with db.read() as conn:
        states = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM work_item_type_state WHERE type_name = 'Epic' ORDER BY ordinal"
            )
        ]
    board = columns(db, None)
    assert [c.state for c in board.columns] == states
    assert {c.state for c in board.columns if c.collapsed} == {"Closed", "Removed"}
    assert all(c.cards == () for c in board.columns)


def test_cards_by_state_and_id(db: Database, store: WorkItemStore, people: People) -> None:
    a = _epic(store, people, "A <b>bold</b>", add(f"/fields/{SUB}", "Awaiting sign-off"))
    b = _epic(store, people, "B")
    store.update(b, [add("/fields/System.State", "T1 Requirements & Outcome")], people.owner)
    store.create("Task", [title("not on the board")], people.service)
    board = columns(db, None)
    by_state = {c.state: c for c in board.columns}
    first = by_state["T0 Intake & Qualification"]
    assert [card.id for card in first.cards] == [a]
    card = first.cards[0]
    assert card.title == "A <b>bold</b>"  # raw text; the template escapes it
    assert card.fields == (("ADLC Sub-stage", "Awaiting sign-off"),)
    assert card.changed_by == "ADLC Platform"
    moved = by_state["T1 Requirements & Outcome"].cards[0]
    assert moved.id == b and moved.fields == () and moved.changed_by == "Product Owner"
    assert first.count == 1 and sum(c.count for c in board.columns) == 2


def test_an_unknown_state_goes_to_other(db: Database, store: WorkItemStore, people: People) -> None:
    item = _epic(store, people, "Odd")
    with db.write() as conn:  # a process change after seeding
        conn.execute("UPDATE work_item SET state = 'Retired stage' WHERE id = ?", (item,))
    board = columns(db, None)
    assert board.columns[-1].state == "Retired stage" and board.columns[-1].other
    assert [c.id for c in board.columns[-1].cards] == [item]


def test_area_filter(db: Database, store: WorkItemStore, people: People) -> None:
    inside = _epic(store, people, "Inside", add("/fields/System.AreaPath", AREA))
    _epic(store, people, "Root")
    filtered = columns(db, AREA)
    assert [card.id for c in filtered.columns for card in c.cards] == [inside]
    assert filtered.area == AREA
    assert len([card for c in columns(db, "Agentic ADLC").columns for card in c.cards]) == 2
    unknown = columns(db, "Nowhere")
    assert unknown.area is None and unknown.notice  # unknown area: unfiltered, with a notice
