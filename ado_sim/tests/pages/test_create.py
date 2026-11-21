"""017 US4: create an Epic from the board (T026; FR-010, SC-003)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ado_sim.workitems import WorkItemStore
from tests.conftest import OWNER
from tests.pages.conftest import BOARD, csrf_of, sign_in

AREA = "Agentic ADLC\\Use cases"


def _create(client: TestClient, **data: str) -> object:
    page = client.get(BOARD)
    return client.post(BOARD + "/epics", data={"csrf": csrf_of(page.text), **data})


def test_created_as_the_signed_in_user(client: TestClient, store: WorkItemStore) -> None:
    sign_in(client)
    answer = _create(client, title="Claims triage", description="Line one\n<b>two</b>", area=AREA)
    assert answer.status_code == 303  # type: ignore[attr-defined]
    item = store.get(1)
    assert item.fields["System.CreatedBy"]["uniqueName"] == OWNER
    assert item.fields["System.AreaPath"] == AREA
    assert item.fields["System.Description"] == "<p>Line one</p><p>&lt;b&gt;two&lt;/b&gt;</p>"
    assert [u.revised_by["uniqueName"] for u in store.updates(1)] == [OWNER]
    assert "Claims triage" in client.get(BOARD).text


def test_refusals_keep_the_values(client: TestClient) -> None:
    sign_in(client)
    answer = _create(client, title="", description="kept text", area=AREA)
    assert answer.status_code == 400  # type: ignore[attr-defined]
    text = answer.text  # type: ignore[attr-defined]
    assert 'role="alert"' in text and "kept text" in text
    wrong_area = _create(client, title="t", description="", area="Nowhere")
    assert wrong_area.status_code == 400  # type: ignore[attr-defined]


def test_only_existing_areas_are_offered(client: TestClient) -> None:
    sign_in(client)
    page = client.get(BOARD, params={"area": AREA}).text
    form = page.split('id="new-area"')[1].split("</select>")[0]
    assert f'value="{AREA}" selected' in form.replace("&#39;", "'")
