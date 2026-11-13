"""012 T016 (FR-007, contracts/api-changes.md): an event an agent proposes waits for a person in
the terminal's accountable role; confirming raises it (and its route runs), dismissing records it;
each is decided once."""

from typing import Any

from tests.support.api import Api
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness

OWNER = "service_owner"  # T8's accountable role (adlc-specs content)


def _propose(h: Harness, api: Api, run: str, *events: tuple[str, str]) -> None:
    h.drain()
    detail = api.get(OWNER, f"/runs/{run}").json()
    rows = [
        {"event_id": e, "event_type": t, "raised_at": "", "routed_to": "T9", "status": "proposed"}
        for e, t in events
    ]
    edited = api.put(
        OWNER,
        f"/runs/{run}/artifacts/raised_events",
        json={"rows": rows, "expected_version": detail["run"]["version"]},
    )
    assert edited.status_code == 200, edited.text
    h.drain()


def _listed(api: Api, role: str) -> list[dict[str, Any]]:
    answer = api.get(role, "/events/proposed")
    assert answer.status_code == 200, answer.text
    found: list[dict[str, Any]] = answer.json()
    return found


def test_confirming_raises_the_event_and_t9_opens(h: Harness, api: Api) -> None:
    usecase, run = walk_to(h, "T8")
    _propose(h, api, run, ("EV-1", "drift"), ("EV-2", "T8.event.cost_overrun"))
    assert [p["event_id"] for p in _listed(api, OWNER)] == ["EV-1", "EV-2"]
    assert _listed(api, "sre") == []  # responsible, not accountable

    confirmed = api.post(OWNER, f"/events/proposed/{run}/EV-1", json={"confirm": True})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["raised_event_id"]
    dismissed = api.post(
        OWNER, f"/events/proposed/{run}/EV-2", json={"confirm": False, "comment": "budget raised"}
    )
    assert dismissed.status_code == 200 and "raised_event_id" not in dismissed.json()
    assert _listed(api, OWNER) == []
    h.drain()
    assert h.active(usecase, "T9").trigger_event_type == "T8.event.drift"


def test_refusals(h: Harness, api: Api) -> None:
    _, run = walk_to(h, "T8")
    _propose(h, api, run, ("EV-1", "drift"))
    assert (
        api.post("sre", f"/events/proposed/{run}/EV-1", json={"confirm": True}).status_code == 403
    )
    assert (
        api.post(OWNER, f"/events/proposed/{run}/EV-9", json={"confirm": True}).status_code == 404
    )
    assert (
        api.post(OWNER, f"/events/proposed/{run}/EV-1", json={"confirm": False}).status_code == 200
    )
    assert (
        api.post(OWNER, f"/events/proposed/{run}/EV-1", json={"confirm": True}).status_code == 409
    )
    assert api.client.get("/events/proposed").status_code == 401
