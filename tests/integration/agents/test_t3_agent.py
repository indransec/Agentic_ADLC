"""011 T013 (US1; FR-004, FR-005, FR-011, FR-012; SC-002, SC-003): the T3 builder adapts the fill
on its branch, opens a pull request, runs CI until green, provisions dev with CI's hash and returns
its artifacts; its controls read the recorded CI result, and a copied value that differs fails."""

import copy
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import text

from adlc.policy.synthetic import load_synthetic_artifacts
from tests.support.acting import acting, tool
from tests.support.orchestration import SYNTHETIC, Harness
from tests.support.pg import PlatformDatabase

SYN = load_synthetic_artifacts(SYNTHETIC)
AGENT = "t3-builder-agent"
FILL = {
    "instructions.md": "Assign each incident to its resolver team; never close incidents.",
    "routing_rules.yaml": "a: 2",
}


def output_of(messages: Sequence[Mapping[str, str]], name: str) -> dict[str, Any]:
    """The latest output of tool ``name`` in the conversation."""
    marker = f'<data source="tool:{name}">'
    for message in reversed(messages):
        content = message["content"]
        if message["role"] == "user" and marker in content:
            body = content[content.index(marker) + len(marker) : content.rindex("</data>")]
            found: dict[str, Any] = json.loads(body)
            return found
    raise AssertionError(f"no {name} output in the conversation")


def create_dev(messages: Sequence[Mapping[str, str]]) -> str:
    return tool("pilot_env_create", {"package_hash": output_of(messages, "ci_run")["package_hash"]})


def artifacts(coverage: float | None = None) -> Any:
    def answer(messages: Sequence[Mapping[str, str]]) -> str:
        ci = output_of(messages, "ci_run")
        rows = copy.deepcopy(SYN["T3"])
        rows["test_results"] = [{"suite": s, **v} for s, v in ci["tests"].items()]
        if coverage is not None:
            rows["test_results"][0]["coverage_pct"] = coverage
        rows["security_build_checks"] = [
            {"scan": s, "tool": "bandit" if s == "sast" else "pattern-scan", **v, "status": "pass"}
            for s, v in ci["scans"].items()
        ]
        rows["observability_check"] = ci["observability"]
        rows["candidate_package"] = [
            {"package_uri": f"pilot-registry://{ci['package_hash']}", "sha256": ci["package_hash"]}
        ]
        return json.dumps({"artifacts": rows})

    return answer


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


BUILD = [
    tool("git_list"),
    tool("git_write", {"files": FILL, "message": "Adapt the example fill to FR-01..FR-03"}),
    tool("git_open_pull_request", {"title": "Use-case fill"}),
    tool("ci_run"),
    create_dev,
    tool("pilot_env_status", {"environment": "dev"}),
]


def test_t3_builds_the_candidate_from_real_ci_evidence(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    with acting(orch_template, {AGENT: [*BUILD, artifacts()]}, (AGENT,), tmp_path) as a:
        usecase, run = to_t3(a.h)
        assert run.state == "awaiting_sign_off", (run.state, run.control_results)
        built = a.pilot.builds[-1]
        assert built["instructions.md"] == FILL["instructions.md"]  # the agent's adapted fill
        candidate = run.artifacts["candidate_package"][0]["sha256"]
        assert (
            candidate in a.pilot.packages
            and a.pilot.hosts["dev"].running["package_hash"] == candidate
        )  # type: ignore[index]
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

    script = [
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
