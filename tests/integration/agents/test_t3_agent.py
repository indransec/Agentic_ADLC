"""011 T013 (US1; FR-004, FR-005, FR-011, FR-012; SC-002, SC-003): the T3 builder adapts the fill
on its branch, opens a pull request, runs CI until green, provisions dev with CI's hash and returns
its artifacts; its controls read the recorded CI result, and a copied value that differs fails."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import text

from tests.support.acting import acting, tool
from tests.support.acting_scripts import FILL, create_dev, output_of, t3_artifacts, t3_build
from tests.support.orchestration import Harness
from tests.support.pg import PlatformDatabase

AGENT = "t3-builder-agent"
BUILD = t3_build()[:-1]  # every step before the final answer
artifacts = t3_artifacts


def to_t3(h: Harness) -> tuple[str, Any]:
    usecase = h.submit()
    h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "medium"})
    h.pass_run(h.active(usecase, "T1").run_id)
    h.pass_run(h.active(usecase, "T2").run_id)
    return usecase, h.active(usecase, "T3")


def decisions(h: Harness, run_id: str) -> dict[str, tuple[bool, bool]]:
    with h.app.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT check_id, passed, synthetic FROM run.policy_decision WHERE run_id = :r AND check_id LIKE 'CTL-T3-%' ORDER BY policy_decision_id"
            ),
            {"r": run_id},
        ).all()
    return {str(c): (bool(p), bool(s)) for c, p, s in rows}


def test_t3_builds_the_candidate_from_real_ci_evidence(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    with acting(orch_template, {AGENT: [*BUILD, artifacts()]}, (AGENT,), tmp_path) as a:
        usecase, run = to_t3(a.h)
        assert run.state == "awaiting_sign_off", (run.state, run.control_results)
        built = a.pilot.builds[-1]
        assert built["instructions.md"] == FILL["instructions.md"]  # the agent's adapted fill
        candidate = run.artifacts["candidate_package"][0]["sha256"]
        dev = a.pilot.hosts["dev"].running or {}
        assert candidate in a.pilot.packages and dev["package_hash"] == candidate
        found = decisions(a.h, run.run_id)
        for check in (
            "CTL-T3-01",
            "CTL-T3-02",
            "CTL-T3-03",
            "CTL-T3-04",
            "CTL-T3-09",
            "CTL-T3-10",
            "CTL-T3-11",
            "CTL-T3-12",
        ):
            assert found[check] == (True, False), check  # passed, not synthetic (SC-003)
        assert not [c for c in run.control_results if not c["passed"]]
        with a.h.app.connect() as conn:
            calls = conn.execute(
                text(
                    "SELECT tool, outcome FROM tools.tool_call WHERE run_id = :r ORDER BY tool_call_id"
                ),
                {"r": run.run_id},
            ).all()
        assert [c[0] for c in calls] == [
            "git_list",
            "git_write",
            "git_open_pull_request",
            "ci_run",
            "pilot_env_create",
            "pilot_env_status",
        ]
        assert all(c[1] == "ok" for c in calls)


def test_a_red_ci_is_fixed_in_a_second_round(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    leaky = {**FILL, "instructions.md": FILL["instructions.md"] + "\napi_key = 'abcd1234efgh5678'"}

    def fix(messages: Sequence[Mapping[str, str]]) -> str:
        ci = output_of(messages, "ci_run")
        assert "package_hash" not in ci and any(not c["passed"] for c in ci["checks"])
        return tool(
            "git_write",
            {
                "files": FILL,
                "message": "Remove the key",
                "parent": output_of(messages, "git_write")["commit"],
            },
        )

    script: list[Any] = [
        tool("git_list"),
        tool("git_write", {"files": leaky, "message": "first"}),
        tool("ci_run"),
        fix,
        tool("ci_run"),
        create_dev,
        artifacts(),
    ]
    with acting(orch_template, {AGENT: script}, (AGENT,), tmp_path) as a:
        _, run = to_t3(a.h)
        assert run.state == "awaiting_sign_off", run.control_results
        assert len(a.pilot.builds) == 2


def test_a_copied_value_that_differs_fails_its_control(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    retry = [tool("ci_run"), artifacts()]  # a retry starts a new conversation: read CI again
    script = [*BUILD, artifacts(coverage=95.0), *retry]
    with acting(orch_template, {AGENT: script}, (AGENT,), tmp_path) as a:
        _, run = to_t3(a.h)
        a.h.drain()
        run = a.h.run(run.run_id)
        assert run.state == "awaiting_sign_off" and run.auto_retries == 1
        found = decisions(a.h, run.run_id)
        assert found["CTL-T3-09"] == (True, False)  # the retry copied CI's value
        with a.h.app.connect() as conn:
            first = conn.execute(
                text(
                    "SELECT passed, reason FROM run.policy_decision WHERE run_id = :r AND check_id = 'CTL-T3-09' ORDER BY policy_decision_id LIMIT 1"
                ),
                {"r": run.run_id},
            ).one()
        assert not first[0] and "coverage_pct 95" in first[1]
