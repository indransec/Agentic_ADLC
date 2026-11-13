"""012 T016 (US2; FR-002, FR-003, FR-005; SC-001, SC-003): the T7 deployment agent deploys the
authorised package, steps through the rollout reading observability after each stage, and
registers the agent; the copied stage metrics and registry entry are checked against the
recordings; a canary breach rolls traffic back at once and the run goes to people."""

import json
from pathlib import Path
from typing import Any

from tests.support.acting import acting
from tests.support.acting_scripts import Deployment
from tests.support.fake_pilot import SYNTHETIC_CANDIDATE, FakePilot, with_candidate
from tests.support.orchestration import Harness
from tests.support.pg import PlatformDatabase

AGENT = "t7-deployment-agent"


def to_t7(h: Harness, tier: str) -> tuple[str, Any]:
    usecase = h.submit()
    h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": tier})
    for terminal in ("T1", "T2", "T3", "T4", "T5", "T6"):
        h.pass_run(h.active(usecase, terminal).run_id)
    return usecase, h.active(usecase, "T7")


def _failed(run: Any) -> dict[str, str]:
    return {c["id"]: c["reason"] for c in run.control_results if not c["passed"]}


def test_t7_releases_the_authorised_package_in_stages(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    fake = with_candidate(FakePilot(), "test")
    with acting(orch_template, {AGENT: Deployment().script()}, (AGENT,), tmp_path, fake) as a:
        usecase, run = to_t7(a.h, "low")
        a.h.drain()
        run = a.h.run(run.run_id)
        assert run.state == "awaiting_sign_off", (run.state, _failed(run))
        assert _failed(run) == {}
        assert fake.hosts["prod-sim"].stable == SYNTHETIC_CANDIDATE  # SC-001: T3's package
        decisions = {c["id"]: c for c in run.control_results}
        assert not decisions["CTL-T7-08"]["synthetic"] and not decisions["CTL-T7-09"]["synthetic"]
        assert "handover_acceptance" not in run.artifacts
        a.h.pass_run(run.run_id)
        assert a.h.run(run.run_id).final_status == "pass"
        assert a.h.active(usecase, "T8") is not None


def test_a_canary_breach_rolls_back_and_goes_to_people(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    fake = with_candidate(FakePilot(), "test")
    stable = fake.hosts["prod-sim"].stable
    deployment = Deployment(pilot=fake, breach_at="canary")
    with acting(
        orch_template, {AGENT: deployment.script(retries=3)}, (AGENT,), tmp_path, fake
    ) as a:
        _, run = to_t7(a.h, "medium")
        a.h.drain()
        run = a.h.run(run.run_id)
        assert run.state == "escalated", run.state  # people decide the rework
        assert "CTL-T7-04" in _failed(run)  # the canary breach
        host = fake.hosts["prod-sim"]
        assert host.split["mode"] == "full" and host.stable == stable  # SC-003: rolled back
        assert "CTL-T7-08" not in _failed(run)  # the breach is the recorded reading


def test_a_copied_metric_that_differs_from_the_reading_fails(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    deployment = Deployment()

    def inflated(messages: Any) -> str:
        found = json.loads(deployment.answer(messages))
        found["artifacts"]["stage_metrics"][0]["actual"] = 0.99
        return json.dumps(found)

    script = deployment.script()[:-1] + [inflated] * 4
    fake = with_candidate(FakePilot(), "test")
    with acting(orch_template, {AGENT: script}, (AGENT,), tmp_path, fake) as a:
        _, run = to_t7(a.h, "low")
        a.h.drain()
        run = a.h.run(run.run_id)
        assert "is not the recorded" in _failed(run).get("CTL-T7-08", ""), _failed(run)
