"""SC-003: concurrent conditional updates and links stay consistent (T045)."""

from __future__ import annotations

import threading
from typing import Any

from ado_sim.errors import AdoError
from ado_sim.workitems import WorkItemStore
from tests.conftest import People, add, title

THREADS = 20


def _race(count: int, action: Any) -> list[Any]:
    barrier = threading.Barrier(count)
    results: list[Any] = [None] * count

    def run(index: int) -> None:
        barrier.wait()
        try:
            results[index] = action(index)
        except AdoError as error:
            results[index] = error

    threads = [threading.Thread(target=run, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def test_one_conditional_update_wins(store: WorkItemStore, people: People) -> None:
    item_id = store.create("Task", [title("contested")], people.service).id
    store.update(item_id, [title("second")], people.owner)

    def update(index: int) -> Any:
        operations = [{"op": "test", "path": "/rev", "value": 2}, title(f"writer {index}")]
        return store.update(item_id, operations, people.lead)

    results = _race(THREADS, update)
    winners = [r for r in results if not isinstance(r, AdoError)]
    refused = [r for r in results if isinstance(r, AdoError)]
    assert len(winners) == 1 and winners[0].rev == 3
    assert [r.status for r in refused] == [412] * (THREADS - 1)
    assert store.get(item_id).rev == 3
    assert [view.rev for view in store.revisions(item_id)] == [1, 2, 3]
    assert [update.rev for update in store.updates(item_id)] == [1, 2, 3]
    assert store.get(item_id).fields["System.Title"] == winners[0].fields["System.Title"]


def test_link_added_while_the_target_changes(store: WorkItemStore, people: People) -> None:
    parent = store.create("Epic", [title("parent")], people.service).id
    child = store.create("Task", [title("child")], people.service).id
    link = add(
        "/relations/-",
        {
            "rel": "System.LinkTypes.Hierarchy-Reverse",
            "url": f"http://h/_apis/wit/workItems/{parent}",
        },
    )
    target_changes = THREADS - 1

    def act(index: int) -> Any:
        if index == 0:
            return store.update(child, [link], people.lead)
        return store.update(parent, [title(f"parent {index}")], people.owner)

    results = _race(THREADS, act)
    assert not [r for r in results if isinstance(r, AdoError)]
    child_view, parent_view = store.get(child), store.get(parent)
    assert [(r.rel, r.target_id) for r in child_view.relations] == [
        ("System.LinkTypes.Hierarchy-Reverse", parent)
    ]
    assert [(r.rel, r.target_id) for r in parent_view.relations] == [
        ("System.LinkTypes.Hierarchy-Forward", child)
    ]
    # The child gets a revision for its link; the parent's side of the link is an update
    # without a revision (as ADO), so the parent's revisions are its own title changes only.
    assert child_view.rev == 2
    assert parent_view.rev == 1 + target_changes
    parent_updates = store.updates(parent)
    assert len(parent_updates) == 1 + target_changes + 1
    linked = [u for u in parent_updates if u.relations]
    assert len(linked) == 1
    assert [u.rev for u in parent_updates] == sorted(u.rev for u in parent_updates)
