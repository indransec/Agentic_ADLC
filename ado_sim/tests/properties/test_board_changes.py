"""017 SC-002: 50 state and sub-stage changes made through the API each show in the next refresh
of the board (T031)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ado_sim.workitems import WorkItemStore
from tests.conftest import People, add, title
from tests.pages.conftest import BOARD, sign_in

STATES = ["T0 Intake & Qualification", "T1 Requirements & Outcome", "T2 Architecture & Design"]


def test_every_api_change_shows_on_the_next_refresh(
    client: TestClient,
    store: WorkItemStore,
    people: People,
) -> None:
    items = [store.create("Epic", [title(f"Case {n}")], people.service).id for n in range(10)]
    sign_in(client)
    for change in range(50):
        item = items[change % len(items)]
        state = STATES[(change + 1) % len(STATES)]
        stage = f"Stage {change}"
        store.update(
            item,
            [add("/fields/System.State", state), add("/fields/Custom.AdlcSubStage", stage)],
            people.service,
        )
        fragment = client.get(BOARD + "/cards", headers={"HX-Request": "true"}).text
        column = fragment.split(state.replace("&", "&amp;") + " <span")[1].split("</section>")[0]
        assert f"Case {items.index(item)}<" in column.replace("</a>", "<") and stage in column, (
            change
        )
