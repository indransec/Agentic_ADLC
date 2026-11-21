"""017 US2: the read-only item page (T022; FR-011, FR-012)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ado_sim.comments import add_comment
from ado_sim.workitems import WorkItemStore
from tests.conftest import People, add, title
from tests.pages import a11y
from tests.pages.conftest import ITEM, sign_in


def test_fields_parent_children_history_and_comments(
    client: TestClient, store: WorkItemStore, people: People
) -> None:
    epic = store.create("Epic", [title("Parent <i>case</i>")], people.service).id
    task = store.create(
        "Task",
        [
            title("Child"),
            add(
                "/relations/-",
                {
                    "rel": "System.LinkTypes.Hierarchy-Reverse",
                    "url": f"http://h/_apis/wit/workItems/{epic}",
                },
            ),
        ],
        people.service,
    ).id
    store.update(epic, [add("/fields/System.Title", "Renamed <i>case</i>")], people.owner)
    add_comment(store, epic, "A <b>comment</b>", people.lead)
    sign_in(client)
    page = client.get(f"{ITEM}{epic}")
    assert page.status_code == 200
    text = page.text
    assert "Renamed &lt;i&gt;case&lt;/i&gt;" in text
    assert f"{ITEM}{task}" in text  # the child is linked
    assert "Product Owner" in text and "ADLC Platform" in text  # who changed it
    assert "A &lt;b&gt;comment&lt;/b&gt;" in text
    assert a11y.problems(text) == []
    child = client.get(f"{ITEM}{task}").text
    assert f"{ITEM}{epic}" in child  # the parent is linked


def test_unknown_item(client: TestClient) -> None:
    sign_in(client)
    assert client.get(f"{ITEM}999").status_code == 404
