"""Links between work items (T030, written before the relation handling)."""

from typing import Any

import pytest

from ado_sim.errors import AdoError
from ado_sim.workitems import WorkItemStore
from tests.conftest import People, title

CHILD = "System.LinkTypes.Hierarchy-Forward"
PARENT = "System.LinkTypes.Hierarchy-Reverse"
SUCCESSOR = "System.LinkTypes.Dependency-Forward"
PREDECESSOR = "System.LinkTypes.Dependency-Reverse"


def link(rel: str, target: int, comment: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {"rel": rel, "url": f"http://sim/o/_apis/wit/workItems/{target}"}
    if comment:
        value["attributes"] = {"comment": comment}
    return {"op": "add", "path": "/relations/-", "value": value}


def rels(store: WorkItemStore, item_id: int) -> list[tuple[str, int]]:
    return [(r.rel, r.target_id) for r in store.get(item_id).relations]


def refused(
    store: WorkItemStore, item_id: int, operations: list[dict[str, Any]], people: People
) -> int:
    with pytest.raises(AdoError) as raised:
        store.update(item_id, operations, people.owner)
    return raised.value.status


def test_child_link_is_recorded_on_both_items(store: WorkItemStore, people: People) -> None:
    epic = store.create("Epic", [title("epic")], people.service).id
    task = store.create("Task", [title("task")], people.service).id
    store.update(task, [link(PARENT, epic, "run")], people.owner)
    assert rels(store, task) == [(PARENT, epic)]
    assert rels(store, epic) == [(CHILD, task)]
    assert store.get(task).rev == 2
    epic_item = store.get(epic)
    assert epic_item.rev == 1  # the other side gets an update, not a revision (as ADO)
    epic_updates = store.updates(epic)
    assert [(u.id, u.rev) for u in epic_updates] == [(1, 1), (2, 1)]
    assert epic_updates[1].relations == {
        "added": [
            {"rel": CHILD, "targetId": task, "attributes": {"isLocked": False, "comment": "run"}}
        ]
    }
    assert epic_updates[1].revised_by["uniqueName"] == people.owner.unique_name
    task_update = store.updates(task)[-1]
    assert task_update.relations["added"][0]["rel"] == PARENT


def test_link_on_create(store: WorkItemStore, people: People) -> None:
    epic = store.create("Epic", [title("epic")], people.service).id
    task = store.create("Task", [title("task"), link(PARENT, epic)], people.service)
    assert rels(store, task.id) == [(PARENT, epic)]
    assert rels(store, epic) == [(CHILD, task.id)]


def test_dependency_links(store: WorkItemStore, people: People) -> None:
    a = store.create("Task", [title("a")], people.service).id
    b = store.create("Task", [title("b")], people.service).id
    store.update(a, [link(SUCCESSOR, b)], people.owner)
    assert rels(store, b) == [(PREDECESSOR, a)]


def test_second_parent_is_refused(store: WorkItemStore, people: People) -> None:
    one = store.create("Epic", [title("1")], people.service).id
    two = store.create("Epic", [title("2")], people.service).id
    task = store.create("Task", [title("t")], people.service).id
    store.update(task, [link(PARENT, one)], people.owner)
    assert refused(store, task, [link(PARENT, two)], people) == 400
    assert refused(store, two, [link(CHILD, task)], people) == 400
    assert rels(store, two) == []
    assert store.get(two).rev == 1


def test_cycle_is_refused(store: WorkItemStore, people: People) -> None:
    a = store.create("Task", [title("a")], people.service).id
    b = store.create("Task", [title("b"), link(PARENT, a)], people.service).id
    c = store.create("Task", [title("c"), link(PARENT, b)], people.service).id
    assert refused(store, a, [link(PARENT, c)], people) == 400
    assert refused(store, c, [link(CHILD, a)], people) == 400


def test_self_and_missing_targets_are_refused(store: WorkItemStore, people: People) -> None:
    a = store.create("Task", [title("a")], people.service).id
    assert refused(store, a, [link(SUCCESSOR, a)], people) == 400
    assert refused(store, a, [link(SUCCESSOR, 999)], people) == 400


def test_refused_link_changes_neither_item(store: WorkItemStore, people: People) -> None:
    a = store.create("Task", [title("a")], people.service).id
    b = store.create("Task", [title("b")], people.service).id
    operations = [
        {"op": "add", "path": "/fields/System.Title", "value": "changed"},
        link(SUCCESSOR, b),
        link(SUCCESSOR, 999),
    ]
    assert refused(store, a, operations, people) == 400
    assert store.get(a).fields["System.Title"] == "a"
    assert rels(store, a) == [] and rels(store, b) == []
    assert len(store.updates(b)) == 1


def test_remove_by_index_removes_both_directions(store: WorkItemStore, people: People) -> None:
    epic = store.create("Epic", [title("e")], people.service).id
    task = store.create("Task", [title("t"), link(PARENT, epic)], people.service).id
    store.update(task, [{"op": "remove", "path": "/relations/0"}], people.owner)
    assert rels(store, task) == [] and rels(store, epic) == []
    assert store.updates(epic)[-1].relations == {
        "removed": [{"rel": CHILD, "targetId": task, "attributes": {"isLocked": False}}]
    }
