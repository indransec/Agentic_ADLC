"""018 SC-002: with 200 use cases (an Epic, two run items and a clarification each: 800 items),
the backlog's first view within 1 s, its refresh within 0.5 s and the form within 0.5 s at the
95th percentile (T018). Measured through the pages, printed in the test summary."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from ado_sim.workitems import WorkItemStore
from tests.conftest import People, add, title
from tests.pages.conftest import ITEM, sign_in
from tests.properties.conftest import percentile

BACKLOG = "/adlc-demo/Agentic%20ADLC/_backlogs/backlog"
PARENT = "System.LinkTypes.Hierarchy-Reverse"
SAMPLES = 30


def _under(target: int) -> dict[str, object]:
    return add("/relations/-", {"rel": PARENT, "url": f"http://h/_apis/wit/workItems/{target}"})


@pytest.mark.no_cover
def test_backlog_and_form_timing(
    client: TestClient,
    store: WorkItemStore,
    people: People,
    measurements: dict[str, str],
) -> None:
    run = 0
    for n in range(200):
        epic = store.create("Epic", [title(f"Case {n}")], people.service).id
        for stage in ("T0", "T1"):
            run = store.create(
                "Feature",
                [
                    title(f"{stage} run {n}"),
                    add("/fields/System.Description", "<p>Decide</p>"),
                    _under(epic),
                ],
                people.service,
            ).id
        store.create("Task", [title(f"Clarify {n}"), _under(run)], people.service)
    sign_in(client)

    def timed(path: str) -> float:
        started = time.perf_counter()
        assert client.get(path, headers={"HX-Request": "true"}).status_code == 200
        return time.perf_counter() - started

    backlog = percentile([timed(BACKLOG) for _ in range(SAMPLES)], 0.95)
    rows = percentile([timed(BACKLOG + "/rows") for _ in range(SAMPLES)], 0.95)
    form = percentile([timed(f"{ITEM}{run}") for _ in range(SAMPLES)], 0.95)
    measurements["018 SC-002 backlog / refresh / form p95 (800 items)"] = (
        f"{backlog * 1000:.1f} ms / {rows * 1000:.1f} ms / {form * 1000:.1f} ms"
    )
    assert backlog < 1.0 and rows < 0.5 and form < 0.5
