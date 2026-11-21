"""018 US3: the backlog page and its refresh (FR-009 to FR-011, FR-013)."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from ado_sim.workitems import WorkItemStore
from tests.conftest import People, add, title
from tests.pages import a11y
from tests.pages.conftest import BOARD, ITEM, sign_in

BACKLOG = "/adlc-demo/Agentic%20ADLC/_backlogs/backlog"
PARENT = "System.LinkTypes.Hierarchy-Reverse"


def _under(target: int) -> dict[str, object]:
    return add("/relations/-", {"rel": PARENT, "url": f"http://h/_apis/wit/workItems/{target}"})


def _tree(store: WorkItemStore, people: People) -> tuple[int, int, int]:
    epic = store.create("Epic", [title("Claims <b>triage</b>")], people.service).id
    run = store.create("Feature", [title("T0 run"), _under(epic)], people.service).id
    ask = store.create("Task", [title("Clarify"), _under(run)], people.service).id
    return epic, run, ask


def test_the_tree(client: TestClient, store: WorkItemStore, people: People) -> None:
    epic, run, ask = _tree(store, people)
    sign_in(client)
    page = client.get(BACKLOG)
    assert page.status_code == 200
    text = page.text
    for item in (epic, run, ask):
        assert f'href="{ITEM}{item}"' in text
    assert text.index(f"{ITEM}{epic}") < text.index(f"{ITEM}{run}") < text.index(f"{ITEM}{ask}")
    assert "Claims &lt;b&gt;triage&lt;/b&gt;" in text
    assert text.count("<details") == 2  # the levels with children
    assert 'hx-trigger="every 5s"' in text
    assert f'href="{BOARD}"' in text
    assert a11y.problems(text) == []


def test_closed_levels_stay_closed_on_refresh(
    client: TestClient, store: WorkItemStore, people: People
) -> None:
    epic, run, _ = _tree(store, people)
    sign_in(client)
    rows = client.get(f"{BACKLOG}/rows", params={"closed": [str(run)]}).text
    assert f'<details data-id="{run}">' in rows  # closed
    assert f'<details data-id="{epic}" open>' in rows
    assert f'name="closed" value="{run}"' in rows  # travels with the next poll
    assert "<html" not in rows


def test_the_filter_is_in_the_address_and_the_poll(
    client: TestClient, store: WorkItemStore, people: People
) -> None:
    inside = store.create(
        "Epic",
        [title("Inside"), add("/fields/System.AreaPath", "Agentic ADLC\\Use cases")],
        people.service,
    ).id
    outside = store.create("Epic", [title("Outside")], people.service).id
    sign_in(client)
    text = client.get(BACKLOG, params={"area": "Agentic ADLC\\Use cases"}).text
    assert f"{ITEM}{inside}" in text and f"{ITEM}{outside}" not in text
    poll = re.search(r'hx-get="([^"]+)"', text)
    assert poll is not None and "area=Agentic%20ADLC%5CUse%20cases" in poll.group(1)


def test_needs_a_session(client: TestClient) -> None:
    assert client.get(BACKLOG).status_code == 303
    assert client.get(f"{BACKLOG}/rows", headers={"HX-Request": "true"}).headers.get("HX-Redirect")
