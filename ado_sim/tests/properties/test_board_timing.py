"""017 SC-001: with 200 Epics, the board's first view within 1 s and each refresh within 0.5 s
at the 95th percentile (T030). Measured through the pages, printed in the test summary."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from ado_sim.workitems import WorkItemStore
from tests.conftest import People, add, title
from tests.pages.conftest import BOARD, sign_in
from tests.properties.conftest import percentile

SAMPLES = 40


@pytest.mark.no_cover
def test_board_timing(
    client: TestClient,
    store: WorkItemStore,
    people: People,
    measurements: dict[str, str],
) -> None:
    states = ["T0 Intake & Qualification", "T1 Requirements & Outcome", "T2 Architecture & Design"]
    for n in range(200):
        item = store.create(
            "Epic",
            [title(f"Case {n}"), add("/fields/Custom.AdlcSubStage", "Building")],
            people.service,
        ).id
        if n % 3:
            store.update(item, [add("/fields/System.State", states[n % 3])], people.service)
    sign_in(client)

    def timed(path: str) -> float:
        started = time.perf_counter()
        assert client.get(path, headers={"HX-Request": "true"}).status_code == 200
        return time.perf_counter() - started

    page = percentile([timed(BOARD) for _ in range(SAMPLES)], 0.95)
    cards = percentile([timed(BOARD + "/cards") for _ in range(SAMPLES)], 0.95)
    measurements["017 SC-001 board / refresh p95 (200 Epics)"] = (
        f"{page * 1000:.1f} ms / {cards * 1000:.1f} ms"
    )
    assert page < 1.0 and cards < 0.5
