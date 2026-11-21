"""017 US2: the board page and its columns (T020; FR-005..FR-007, FR-012)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ado_sim.workitems import WorkItemStore
from tests.conftest import People, add, title
from tests.pages import a11y
from tests.pages.conftest import BOARD, sign_in


def test_columns_cards_and_escaping(
    client: TestClient, store: WorkItemStore, people: People
) -> None:
    store.create(
        "Epic",
        [title("<script>x</script> case"), add("/fields/Custom.AdlcSubStage", "<b>Awaiting</b>")],
        people.service,
    )
    sign_in(client)
    page = client.get(BOARD)
    assert page.status_code == 200
    text = page.text
    assert "T0 Intake &amp; Qualification" in text
    assert "&lt;script&gt;x&lt;/script&gt; case" in text and "<script>x</script>" not in text
    assert "&lt;b&gt;Awaiting&lt;/b&gt;" in text
    assert "<details" in text  # collapsed columns
    assert "draggable" not in text and "hx-post" not in text.split('id="columns"')[1]  # FR-007
    assert a11y.problems(text) == []


def test_two_hundred_epics_render(client: TestClient, store: WorkItemStore, people: People) -> None:
    for n in range(200):
        store.create("Epic", [title(f"Case {n}")], people.service)
    sign_in(client)
    page = client.get(BOARD)
    assert page.status_code == 200 and page.text.count('class="card"') == 200


def test_unknown_project(client: TestClient) -> None:
    sign_in(client)
    assert client.get("/adlc-demo/Elsewhere/_boards/board").status_code == 404
