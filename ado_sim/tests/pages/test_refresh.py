"""017 US3: the board keeps up (T024; FR-008)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ado_sim.workitems import WorkItemStore
from tests.conftest import People, add, title
from tests.pages.conftest import BOARD, sign_in

CARDS = BOARD + "/cards"


def test_the_board_polls_its_columns(client: TestClient) -> None:
    sign_in(client)
    page = client.get(BOARD).text
    assert 'hx-trigger="every 5s"' in page and f'hx-get="{CARDS}"' in page
    assert 'id="stale"' in page and "/_static/board.js" in page


def test_the_fragment_follows_an_api_change(
    client: TestClient, store: WorkItemStore, people: People
) -> None:
    item = store.create("Epic", [title("Moving")], people.service).id
    sign_in(client)
    before = client.get(CARDS, headers={"HX-Request": "true"}).text
    store.update(
        item,
        [
            add("/fields/System.State", "T1 Requirements & Outcome"),
            add("/fields/Custom.AdlcSubStage", "Building"),
        ],
        people.service,
    )
    after = client.get(CARDS, headers={"HX-Request": "true"}).text
    assert before != after and "Building" in after
    column = after.split("T1 Requirements &amp; Outcome")[1].split("</section>")[0]
    assert "Moving" in column


def test_open_columns_stay_open(client: TestClient) -> None:
    sign_in(client)
    fragment = client.get(CARDS, params=[("open", "Closed")]).text
    closed = fragment.split(">Closed ")[0].rsplit("<details", 1)[1]
    assert " open" in closed


def test_an_expired_session_redirects_the_poll(client: TestClient) -> None:
    answer = client.get(CARDS, headers={"HX-Request": "true"})
    assert answer.headers["HX-Redirect"] == "/_signin"
