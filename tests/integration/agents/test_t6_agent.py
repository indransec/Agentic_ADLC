"""012 T013 (US1; FR-002, FR-004, FR-012; SC-001, SC-004): the T6 readiness agent raises the
change and configures monitors; the run reaches sign-off while the change is still new, pass waits
for the change approval, and the approval re-runs the controls; the gate evidence summary and the
release authorisation are built from records, never written by the agent."""

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from adlc.inbox.changes import ChangeService
from adlc.orchestration.interfaces import EvalContext
from adlc.orchestration.states import InvalidTransition
from adlc.policy.evidence import Evidence, SqlEvidenceProvider
from adlc.spec_toolkit.registry import SqlSpecRegistry
from tests.support.acting import acting
from tests.support.acting_scripts import Readiness
from tests.support.fake_pilot import FakePilot, with_candidate
from tests.support.orchestration import Harness, person
from tests.support.pg import PlatformDatabase

AGENT = "t6-readiness-agent"
CANDIDATE = "sha256:" + "5a" * 32


def to_t6(h: Harness) -> tuple[str, Any]:
    usecase = h.submit()
    h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "low"})
    for terminal in ("T1", "T2", "T3", "T4", "T5"):
        h.pass_run(h.active(usecase, terminal).run_id)
    return usecase, h.active(usecase, "T6")


def _record(h: Harness, usecase: str, terminal: str, run_id: str) -> Any:
    answer = SqlEvidenceProvider(h.app, SqlSpecRegistry(h.app), h.clock).get(
        terminal, EvalContext("T7", "x", run_id, usecase)
    )
    assert isinstance(answer, Evidence)
    return answer.value


def test_t6_waits_for_the_change_approval_then_releases(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    with acting(
        orch_template,
        {AGENT: Readiness().script()},
        (AGENT,),
        tmp_path,
        with_candidate(FakePilot(), "test"),  # T3 and T4 (stubs) left it running
    ) as a:
        usecase, run = to_t6(a.h)
        a.h.drain()
        run = a.h.run(run.run_id)
        assert run.state == "awaiting_sign_off", run.state
        failed = {c["id"]: c for c in run.control_results if not c["passed"]}
        assert set(failed) == {"CTL-T6-07"}, failed  # only the change approval
        assert failed["CTL-T6-07"]["awaits"]
        assert "gate_evidence_summary" not in run.artifacts
        assert "release_authorisation" not in run.artifacts
        assert run.artifacts["deployment_package"][0]["sha256"] == CANDIDATE

        with pytest.raises(InvalidTransition, match="CTL-T6-07"):
            a.h.service.decide(person("release_manager"), run.run_id, "pass")

        changes = ChangeService(a.h.app, SqlSpecRegistry(a.h.app), a.h.service, a.h.clock)
        waiting = changes.waiting(person("release_manager"))
        assert [c["usecase_id"] for c in waiting] == [usecase]
        changes.decide(person("release_manager"), waiting[0]["change_id"], True, "agreed")
        assert a.h.run(run.run_id).controls_pending
        a.h.clock.advance(timedelta(minutes=1))  # inside the change window
        a.h.drain()
        run = a.h.run(run.run_id)
        assert not run.controls_pending
        assert all(c["passed"] for c in run.control_results if c["blocking"]), run.control_results
        a.h.pass_run(run.run_id)
        assert a.h.run(run.run_id).final_status == "pass"

        t7 = a.h.active(usecase, "T7")
        record = _record(a.h, usecase, "T6", t7.run_id)
        summary = {r["terminal"]: r for r in record["gate_evidence_summary"]}
        assert sorted(summary) == ["T0", "T1", "T2", "T3", "T4", "T5"]
        assert all(r["status"] == "pass" and r["signed_by"] for r in summary.values())
        roles = {r["role"] for r in record["release_authorisation"]}
        assert roles == {"release_manager", "service_owner", "business_owner"}
        release = SqlEvidenceProvider(a.h.app, SqlSpecRegistry(a.h.app), a.h.clock).get(
            "release", EvalContext("T7", "x", t7.run_id, usecase)
        )
        assert isinstance(release, Evidence) and release.value["package_sha256"] == CANDIDATE


def test_a_waiver_expiring_before_the_release_fails_ctl_t6_02(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    later = Readiness(window_in=timedelta(days=3))  # the release is three days away
    with acting(
        orch_template,
        {AGENT: later.script()},
        (AGENT,),
        tmp_path,
        with_candidate(FakePilot(), "test"),  # T3 and T4 (stubs) left it running
    ) as a:
        usecase = a.h.submit()
        a.h.pass_run(a.h.active(usecase, "T0").run_id, {"risk_tier": "low"})
        for terminal in ("T1", "T2", "T3", "T4"):
            a.h.pass_run(a.h.active(usecase, terminal).run_id)
        t5 = a.h.active(usecase, "T5").run_id
        a.h.drain()
        expiring = {
            "risk_acceptance": "accepted",
            "expiry": (a.h.clock.now() + timedelta(days=1)).date().isoformat(),
            "compensating_control": "none",
        }
        a.h.service.decide(person("security_officer"), t5, "exception", reason="r", fields=expiring)
        a.h.drain()
        a.h.service.decide_waiver(person("risk_owner"), "WVR-0001", True, "short")
        a.h.drain()
        run = a.h.run(a.h.active(usecase, "T6").run_id)
        failed = {c["id"]: c["reason"] for c in run.control_results if not c["passed"]}
        assert "WVR-0001" in failed.get("CTL-T6-02", ""), failed
