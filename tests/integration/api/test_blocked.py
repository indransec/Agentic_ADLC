"""T044: blocked runs reach their accountable owner, with the reason (change request 2026-11-11)."""

from typing import Any

from tests.support.api import Api
from tests.support.orchestration import Harness

SHORT = "Too short to describe the problem."  # under T0's intake length prerequisite


def blocked(api: Api, role: str) -> list[dict[str, Any]]:
    return [i for i in api.get(role, "/inbox").json() if i["kind"] == "blocked"]


def test_blocked_run_reaches_the_accountable_owner_with_the_reason(h: Harness, api: Api) -> None:
    usecase = api.post(
        "business_owner", "/usecases", json={"name": "Short", "intake_text": SHORT}
    ).json()["usecase_id"]
    h.drain()
    run = f"{usecase}/T0/run-1"
    assert h.run(run).state == "blocked"
    items = blocked(api, "business_owner")  # T0's accountable role
    assert [(i["run_id"], i["role"]) for i in items] == [(run, "business_owner")]
    assert blocked(api, "product_owner") == [] and blocked(api, "sre") == []

    shown = api.get("sre", f"/runs/{run}").json()
    unmet = [p for p in shown["prerequisites"] if p["passed"] is False]
    assert unmet and unmet[0]["description"] and unmet[0]["on_missing"] == "block"
    assert all(
        {"id", "description", "evidence_ref", "passed", "reason"} <= set(p)
        for p in shown["prerequisites"]
    )

    form = api.get("business_owner", f"/runs/{run}").json()["form"]
    assert form["can_terminate"] and not form["can_decide"]
    ended = api.post(
        "business_owner",
        f"/runs/{run}/decisions",
        json={
            "decision": "terminate",
            "comment": "resubmitting with a full description",
            "expected_version": shown["run"]["version"],
        },
    )
    assert ended.status_code == 200, ended.text
    h.drain()
    assert blocked(api, "business_owner") == []


def test_a_run_that_met_its_prerequisites_shows_them_passed(h: Harness, api: Api) -> None:
    usecase = h.submit()
    shown = api.get("sre", f"/runs/{usecase}/T0/run-1").json()
    assert shown["prerequisites"] and all(p["passed"] for p in shown["prerequisites"])
