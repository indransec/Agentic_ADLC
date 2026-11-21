"""018 T012: the backlog tree (FR-009, FR-010; research R-08)."""

from __future__ import annotations

from ado_sim.db import Database
from ado_sim.pages.backlog import TreeRow, tree
from ado_sim.workitems import WorkItemStore
from tests.conftest import People, add, title

PARENT = "System.LinkTypes.Hierarchy-Reverse"


def _under(target: int) -> dict[str, object]:
    return add("/relations/-", {"rel": PARENT, "url": f"http://h/_apis/wit/workItems/{target}"})


def _ids(rows: tuple[TreeRow, ...]) -> list[object]:
    return [(r.id, _ids(r.children)) if r.children else r.id for r in rows]


def _all(rows: tuple[TreeRow, ...]) -> set[int]:
    return {r.id for r in rows} | {i for r in rows for i in _all(r.children)}


def test_roots_and_descendants(store: WorkItemStore, people: People, db: Database) -> None:
    epic = store.create("Epic", [title("Use case")], people.service).id
    run2 = store.create("Feature", [title("Run 2"), _under(epic)], people.service).id
    run1 = store.create("Feature", [title("Run 1"), _under(epic)], people.service).id
    ask = store.create("Task", [title("Ask"), _under(run2)], people.service).id
    stray = store.create("Task", [title("Stray")], people.service).id  # not of the board type
    other = store.create("Epic", [title("Second")], people.service).id
    backlog = tree(db, None)
    assert _ids(backlog.rows) == [(epic, [(run2, [ask]), run1]), other]
    assert stray not in _all(backlog.rows)
    first = backlog.rows[0]
    assert (first.type, first.title, first.state) == (
        "Epic",
        "Use case",
        "T0 Intake & Qualification",
    )


def test_the_area_filter_applies_to_the_top_items(
    store: WorkItemStore, people: People, db: Database
) -> None:
    inside = store.create(
        "Epic",
        [title("In"), add("/fields/System.AreaPath", "Agentic ADLC\\Use cases")],
        people.service,
    ).id
    child = store.create(
        "Feature", [title("Child at the root area"), _under(inside)], people.service
    ).id
    store.create("Epic", [title("Out")], people.service)
    backlog = tree(db, "agentic adlc\\use cases")
    assert _ids(backlog.rows) == [(inside, [child])]
    assert backlog.area == "Agentic ADLC\\Use cases"
    assert tree(db, "Nowhere").notice is not None


def test_a_cycle_in_stored_links_never_loops(
    store: WorkItemStore, people: People, db: Database
) -> None:
    epic = store.create("Epic", [title("Use case")], people.service).id
    run = store.create("Feature", [title("Run"), _under(epic)], people.service).id
    task = store.create("Task", [title("Ask"), _under(run)], people.service).id
    with db.write() as conn:  # impossible through the API: the run also under its own task
        conn.execute(
            "INSERT INTO relation (source_id, target_id, rel, attributes) VALUES (?, ?, ?, '{}')",
            (run, task, PARENT),
        )
    assert _ids(tree(db, None).rows) == [(epic, [(run, [task])])]
