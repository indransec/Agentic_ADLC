"""Updates and revisions recorded by the store (T023, written before the history reads)."""

import sqlite3

import pytest

from ado_sim.db import Database
from ado_sim.workitems import WorkItemStore
from tests.conftest import People, add, title


def test_one_update_per_change_with_old_and_new_values(
    store: WorkItemStore, people: People
) -> None:
    item = store.create("Task", [title("first")], people.service)
    store.update(item.id, [add("/fields/System.Title", "second")], people.owner)
    store.update(item.id, [add("/fields/System.State", "Active")], people.lead)
    updates = store.updates(item.id)
    assert [(u.id, u.rev, u.revised_by["uniqueName"]) for u in updates] == [
        (1, 1, people.service.unique_name),
        (2, 2, people.owner.unique_name),
        (3, 3, people.lead.unique_name),
    ]
    creation = updates[0].fields
    assert creation["System.Title"] == {"newValue": "first"}
    assert all("oldValue" not in change for change in creation.values())
    assert updates[1].fields["System.Title"] == {"oldValue": "first", "newValue": "second"}
    assert updates[1].fields["System.Rev"] == {"oldValue": 1, "newValue": 2}
    assert updates[2].fields["System.State"] == {"oldValue": "New", "newValue": "Active"}
    assert (
        updates[2].fields["System.ChangedBy"]["newValue"]["uniqueName"] == people.lead.unique_name
    )


def test_revised_dates(store: WorkItemStore, people: People) -> None:
    item = store.create("Task", [title("a")], people.service)
    second = store.update(item.id, [add("/fields/System.Title", "b")], people.owner)
    updates = store.updates(item.id)
    assert updates[0].revised_date == second.fields["System.ChangedDate"]
    assert updates[1].revised_date == "9999-01-01T00:00:00Z"


def test_revisions_reproduce_the_item(store: WorkItemStore, people: People) -> None:
    item = store.create("Task", [title("a")], people.service)
    after_one = store.get(item.id)
    store.update(item.id, [add("/fields/System.Title", "b")], people.owner)
    after_two = store.get(item.id)
    revisions = store.revisions(item.id)
    assert [r.rev for r in revisions] == [1, 2]
    assert revisions[0].fields == after_one.fields
    assert revisions[1].fields == after_two.fields
    assert store.revision(item.id, 1).fields == after_one.fields


def test_no_revision_for_no_change(store: WorkItemStore, people: People) -> None:
    item = store.create("Task", [title("a")], people.service)
    store.update(item.id, [add("/fields/System.Title", "a")], people.owner)
    assert store.get(item.id).rev == 1
    assert len(store.updates(item.id)) == 1


def test_changed_dates_strictly_increase_when_the_clock_repeats(
    db: Database, people: People
) -> None:
    frozen = WorkItemStore(db, clock=lambda: "2026-11-20T10:00:00.000000Z")
    item = frozen.create("Task", [title("a")], people.service)
    dates = [item.fields["System.ChangedDate"]]
    for value in ("b", "c", "d"):
        dates.append(
            frozen.update(item.id, [add("/fields/System.Title", value)], people.owner).fields[
                "System.ChangedDate"
            ]
        )
    assert dates == [
        "2026-11-20T10:00:00.000000Z",
        "2026-11-20T10:00:00.000001Z",
        "2026-11-20T10:00:00.000002Z",
        "2026-11-20T10:00:00.000003Z",
    ]


def test_history_rows_cannot_be_changed(store: WorkItemStore, people: People, db: Database) -> None:
    store.create("Task", [title("a")], people.service)
    with pytest.raises(sqlite3.IntegrityError), db.write() as conn:
        conn.execute("UPDATE work_item_update SET revised_by = 'x'")


def test_as_of(store: WorkItemStore, people: People) -> None:
    item = store.create("Task", [title("a")], people.service)
    first_date = item.fields["System.ChangedDate"]
    store.update(item.id, [add("/fields/System.Title", "b")], people.owner)
    assert store.get(item.id, as_of=first_date).fields["System.Title"] == "a"
    assert store.get(item.id).fields["System.Title"] == "b"
