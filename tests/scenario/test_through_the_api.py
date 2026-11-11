"""007 T032: the sample lifecycle T0-T8 driven through the API operations only (SC-003, SC-005,
SC-008).

Only the orchestrator worker (``h.drain``) advances runs, as in production. Every person action
goes through the API: submission, finding the item in the inbox, reading the run detail, and the
decision with the version that was read.
"""

from pathlib import Path
from typing import Any

from adlc.identity.catalogue import load_role_ids
from tests.support.api import ROLES, Api, api_for
from tests.support.orchestration import Harness

LIFECYCLE = ["T0", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]
SA_8_2 = {
    "artifacts",
    "control_results",
    "recommendation",
    "prior_rework",
    "clarifications",
    "approvals",
    "timer",
    "cost",
    "timeline",
    "form",
    "run",
}
INTAKE = "Claims handlers spend twelve minutes triaging each claim before an assessor sees it. " * 4
TYPED = {"risk_tier": "medium"}  # T0's typed value; others get a placeholder


def approver(api: Api, roles: list[str], run_id: str) -> str | None:
    for role in roles:
        if any(
            i["run_id"] == run_id and i["kind"] == "sign_off"
            for i in api.get(role, "/inbox").json()
        ):
            return role
    return None


def active(api: Api, usecase: str, terminal: str) -> dict[str, Any]:
    runs = api.get("sre", f"/usecases/{usecase}").json()["runs"]
    (run,) = [r for r in runs if r["terminal_id"] == terminal and r["state"] != "closed"]
    return dict(run)


def test_lifecycle_through_the_api(h: Harness, tmp_path: Path) -> None:
    roles = sorted(load_role_ids(ROLES))
    with api_for(h, tmp_path) as api:
        submitted = api.post(
            "business_owner", "/usecases", json={"name": "Claims", "intake_text": INTAKE}
        )
        assert submitted.status_code == 201, submitted.text
        usecase = submitted.json()["usecase_id"]
        h.drain()
        for terminal in LIFECYCLE:
            run_id = active(api, usecase, terminal)["run_id"]
            first = api.get("sre", f"/runs/{run_id}").json()
            assert set(first) >= SA_8_2, terminal
            assert first["run"]["state"] == "awaiting_sign_off", (terminal, first["run"]["state"])
            assert first["recommendation"] is not None and first["artifacts"], terminal
            for _ in range(8):
                role = approver(api, roles, run_id)
                if role is None:
                    break
                shown = api.get(role, f"/runs/{run_id}").json()
                fields = {n: TYPED.get(n, f"{n} (typed)") for n in shown["form"]["typed_fields"]}
                answer = api.post(
                    role,
                    f"/runs/{run_id}/decisions",
                    json={
                        "decision": "pass",
                        "fields": fields,
                        "expected_version": shown["run"]["version"],
                    },
                )
                assert answer.status_code == 200, (terminal, role, answer.text)
            h.drain()
            closed = api.get("sre", f"/runs/{run_id}").json()["run"]
            assert closed["final_status"] == "pass", (terminal, closed)
        journey = api.get("business_owner", f"/usecases/{usecase}").json()
        assert [r["terminal_id"] for r in journey["runs"] if r["state"] == "closed"] == LIFECYCLE
        assert journey["usecase"]["risk_tier"] == "medium"
        report = api.post("sre", f"/usecases/{usecase}/verify").json()
        assert report["verified"] and report["records_checked"] >= len(LIFECYCLE)
