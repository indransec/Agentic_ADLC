"""012 T026 (US4, US5; FR-008, FR-009; SC-006): the T9 evolution agent classifies a drift event
and the lifecycle re-enters at the class's terminal; a retirement revokes the identity and tool
scopes, disposes of the data and retires the registry entry, and the retirement controls read
those records; revocation is refused outside a retirement."""

from pathlib import Path
from typing import Any

from sqlalchemy import text

from adlc.orchestration.service import Actor
from adlc.tools.enterprise.records import EnterpriseStore
from adlc.tools.token import Claims
from tests.integration.agents.test_t8_agent import _pilot
from tests.support.acting import acting
from tests.support.acting_scripts import Evolution
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, person
from tests.support.pg import PlatformDatabase

AGENT = "t9-evolution-agent"


def _released(h: Harness, usecase: str, dependant_owner: str = "other-team") -> None:
    """What T7 (a stub here) leaves: the registry entry and the CMDB item; another use case's
    agent depends on this one."""
    store = EnterpriseStore(h.app)
    claims = Claims(f"{usecase}/T7/run-1", usecase, "T7", 1, ())
    agent = store.add(
        "agent_registry",
        "agent",
        "AG",
        claims,
        {"name": "triage", "owner": "service_owner", "status": "live"},
    )
    store.add("cmdb", "ci", "CI", claims, {"name": "triage", "data_status": "live"})
    other = Claims("UC-0999/T7/run-1", "UC-0999", "T7", 1, ())
    store.add(
        "agent_registry",
        "agent",
        "AG",
        other,
        {"name": "reporting", "owner": dependant_owner, "depends_on": agent["id"]},
    )


def _failed(run: Any) -> dict[str, str]:
    return {c["id"]: c["reason"] for c in run.control_results if not c["passed"]}


def _decisions(h: Harness, run_id: str) -> dict[str, bool]:
    with h.app.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT check_id, synthetic FROM run.policy_decision WHERE run_id = :r AND check_id LIKE 'CTL-T9-%'"
            ),
            {"r": run_id},
        ).all()
    return {str(c): bool(s) for c, s in rows}


def test_drift_is_classified_and_reenters_at_t2(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    script = Evolution(revoke_in_evolve=True).script()
    with acting(orch_template, {AGENT: script}, (AGENT,), tmp_path, _pilot()) as a:
        usecase, _ = walk_to(a.h, "T8", tier="low")
        _released(a.h, usecase)
        a.h.service.raise_operational_event(
            Actor.system("monitor"), usecase, "drift", {"monitor_id": "MON-04"}
        )
        a.h.drain()
        run = a.h.active(usecase, "T9")
        assert run.mode == "evolve" and run.state == "awaiting_sign_off", (run.state, _failed(run))
        assert _failed(run) == {}
        with a.h.app.connect() as conn:
            refused = conn.execute(
                text(
                    "SELECT outcome, reason FROM tools.tool_call WHERE run_id = :r AND tool = 'iam_revoke'"
                ),
                {"r": run.run_id},
            ).all()
            revocations = conn.execute(
                text("SELECT count(*) FROM tools.enterprise_record WHERE system = 'iam'")
            ).scalar_one()
        assert [o for o, _ in refused] == ["refused"] and "retire" in refused[0][1]  # SC-006
        assert revocations == 0
        a.h.pass_run(run.run_id)
        assert a.h.active(usecase, "T2") is not None  # re-entry at the moderate class's terminal


def _retire(a: Any, dependant_owner: str = "other-team") -> tuple[str, Any]:
    usecase, t8 = walk_to(a.h, "T8", tier="low")
    _released(a.h, usecase, dependant_owner)
    a.h.drain()
    a.h.service.decide(person("business_owner"), t8, "terminate", comment="retire the agent")
    a.h.drain()
    run = a.h.active(usecase, "T9")
    return usecase, a.h.run(run.run_id)


def test_retirement_revokes_disposes_and_is_checked(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    with acting(
        orch_template,
        {AGENT: Evolution(retire=True).script()},
        (AGENT,),
        tmp_path,
        _pilot(),
    ) as a:
        usecase, run = _retire(a)
        assert run.mode == "retire" and run.state == "awaiting_sign_off", (run.state, _failed(run))
        assert _failed(run) == {}
        decisions = _decisions(a.h, run.run_id)
        assert not any(
            decisions[c] for c in ("CTL-T9-04", "CTL-T9-05", "CTL-T9-06")
        )  # real records
        store = EnterpriseStore(a.h.app)
        assert {r["what"] for r in store.records("iam", usecase, "revocation")} == {
            "identity",
            "tool_scopes",
        }
        assert store.records("agent_registry", usecase)[0]["status"] == "retired"
        assert "closure_report" not in run.artifacts


def test_an_unowned_dependant_fails_ctl_t9_06(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    with acting(
        orch_template,
        {AGENT: Evolution(retire=True).script(retries=3)},
        (AGENT,),
        tmp_path,
        _pilot(),
    ) as a:
        _, run = _retire(a, dependant_owner="")
        assert "CTL-T9-06" in _failed(run), _failed(run)
