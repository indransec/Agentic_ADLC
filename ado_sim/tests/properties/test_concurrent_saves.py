"""018 SC-003: two people open the same form and save different changes; in every pair the
second save gets the conflict with its values kept, and nothing is overwritten silently (T019)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ado_sim.workitems import WorkItemStore
from tests.conftest import People, title
from tests.pages.conftest import ITEM, sign_in
from tests.pages.test_form_page import _fields

PAIRS = (
    ("Custom.AdlcDecision", "Pass", "Custom.AdlcDecision", "Rework"),
    ("Custom.AdlcComment", "first", "Custom.AdlcComment", "second"),
    ("System.Title", "Renamed once", "Custom.AdlcReason", "a reason"),
    ("Custom.AdlcValues", "a: 1", "System.State", "Active"),
    ("System.Description", "one", "System.Description", "two"),
)


def test_the_second_save_always_gets_the_conflict(
    client: TestClient, store: WorkItemStore, people: People
) -> None:
    owner = sign_in(client)
    lead = sign_in(TestClient(client.app, follow_redirects=False), "engineering.lead@adlc.demo")
    for first_ref, first_value, second_ref, second_value in PAIRS:
        item = store.create("Feature", [title("Run")], people.service).id
        first, second = (
            _fields(owner.get(f"{ITEM}{item}").text),
            _fields(lead.get(f"{ITEM}{item}").text),
        )
        first[first_ref] = first_value
        second[second_ref] = second_value
        assert owner.post(f"{ITEM}{item}", data=first).status_code == 303
        refused = lead.post(f"{ITEM}{item}", data=second)
        assert refused.status_code == 412, (first_ref, second_ref)
        assert _fields(refused.text)[second_ref] == second_value  # kept
        current = store.get(item)
        assert current.rev == 2  # only the first save
        stored = current.fields.get(first_ref)
        assert stored is not None and first_value in str(stored)
