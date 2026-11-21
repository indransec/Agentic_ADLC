"""017 US5: the area filter (T028; FR-009)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ado_sim.workitems import WorkItemStore
from tests.conftest import People, add, title
from tests.pages.conftest import BOARD, sign_in

AREA = "Agentic ADLC\\Use cases"


def test_the_filter(client: TestClient, store: WorkItemStore, people: People) -> None:
    store.create("Epic", [title("Inside"), add("/fields/System.AreaPath", AREA)], people.service)
    store.create("Epic", [title("At the root")], people.service)
    sign_in(client)
    filtered = client.get(BOARD, params={"area": AREA}).text
    assert "Inside" in filtered and "At the root" not in filtered
    assert "area=Agentic%20ADLC%5CUse%20cases" in filtered  # the poll keeps the filter
    everything = client.get(BOARD).text
    assert "Inside" in everything and "At the root" in everything
    unknown = client.get(BOARD, params={"area": "Nowhere"}).text
    assert "There is no area path" in unknown and "At the root" in unknown
