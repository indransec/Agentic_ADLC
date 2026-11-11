"""T010: submit and follow a use case through the API (US1; FR-001, FR-004, FR-005; SC-006)."""

import pytest

from tests.support.api import Api
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness

INTAKE = "Claims handlers spend twelve minutes triaging each claim. " * 5


def test_submit_opens_t0_and_the_journey_shows_it(h: Harness, api: Api) -> None:
    answer = api.post("business_owner", "/usecases", json={"name": "Claims", "intake_text": INTAKE})
    assert answer.status_code == 201, answer.text
    usecase = answer.json()["usecase_id"]
    h.drain()
    journey = api.get("sre", f"/usecases/{usecase}").json()  # any signed-in person may read
    assert journey["usecase"]["name"] == "Claims"
    assert [(r["terminal_id"], r["state"]) for r in journey["runs"]] == [
        ("T0", "awaiting_sign_off")
    ]
    assert {"summary", "cost"} <= set(journey)


def test_only_the_accountable_role_submits(api: Api) -> None:
    refused = api.post("sre", "/usecases", json={"name": "x", "intake_text": INTAKE})
    assert refused.status_code == 403 and refused.json()["kind"] == "not_allowed"


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"name": "", "intake_text": INTAKE}, "name"),
        ({"name": "x" * 201, "intake_text": INTAKE}, "name"),
        ({"name": "x", "intake_text": ""}, "intake_text"),
        ({"name": "x"}, "intake_text"),
    ],
)
def test_input_limits(api: Api, body: dict[str, str], field: str) -> None:
    answer = api.post("business_owner", "/usecases", json=body)
    assert answer.status_code == 422 and answer.json()["field"] == field


def test_my_use_cases(h: Harness, api: Api) -> None:
    usecase, _ = walk_to(h, "T2")
    other = api.post("business_owner", "/usecases", json={"name": "Other", "intake_text": INTAKE})
    mine = [u["usecase_id"] for u in api.get("business_owner", "/usecases?mine=true").json()]
    assert other.json()["usecase_id"] in mine
    # The engineering lead holds a role in T2, which this use case has reached; not the other one.
    lead = [u["usecase_id"] for u in api.get("engineering_lead", "/usecases?mine=true").json()]
    assert usecase in lead and other.json()["usecase_id"] not in lead
    everyone = [u["usecase_id"] for u in api.get("sre", "/usecases").json()]
    assert {usecase, other.json()["usecase_id"]} <= set(everyone)
    assert api.get("sre", "/usecases/UC-9999").status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/usecases"),
        ("post", "/usecases"),
        ("get", "/usecases/UC-0001"),
        ("get", "/inbox"),
        ("get", "/runs/UC-0001/T0/run-1"),
        ("post", "/runs/UC-0001/T0/run-1/decisions"),
    ],
)
def test_no_session_no_access(api: Api, method: str, path: str) -> None:
    """SC-006: only health and sign-in answer without a session."""
    answer = getattr(api.client, method)(path)
    assert answer.status_code == 401
