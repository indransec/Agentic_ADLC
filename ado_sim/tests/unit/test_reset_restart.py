"""US7: data survives a restart (SC-005); reset only through the confirmed command (T038)."""

from pathlib import Path

from ado_sim.comments import add_comment
from ado_sim.db import Database
from ado_sim.workitems import WorkItemStore
from tests.conftest import People, title

PARENT = "System.LinkTypes.Hierarchy-Reverse"


def test_everything_survives_closing_and_reopening(
    db: Database, store: WorkItemStore, people: People
) -> None:
    epic = store.create("Epic", [title("e")], people.service).id
    task = store.create(
        "Task",
        [
            title("t"),
            {
                "op": "add",
                "path": "/relations/-",
                "value": {"rel": PARENT, "url": f"http://h/_apis/wit/workItems/{epic}"},
            },
        ],
        people.service,
    ).id
    store.update(task, [title("t2")], people.owner)
    add_comment(store, task, "kept", people.lead)
    before = (store.get(task), store.updates(task), store.revisions(task), store.get(epic))
    path = Path(db.path)
    db.close()
    reopened = WorkItemStore(Database(path))
    after = (
        reopened.get(task),
        reopened.updates(task),
        reopened.revisions(task),
        reopened.get(epic),
    )
    assert after == before
    reopened.db.close()
