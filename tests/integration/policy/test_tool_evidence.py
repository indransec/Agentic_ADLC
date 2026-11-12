"""011 T004 (FR-010, FR-011; contracts/evidence-sources.md): ci, sbom, harness, redteam and dlp
come from the recorded tool results for the use case's candidate; with none recorded they are not
available (so synthetic evidence, labelled, is the fallback)."""

import json
from typing import Any

from sqlalchemy import text

from adlc.orchestration.interfaces import EvalContext
from adlc.policy.evidence import Evidence, SqlEvidenceProvider
from adlc.policy.values import NOT_AVAILABLE
from adlc.spec_toolkit.registry import SqlSpecRegistry
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness

OTHER = "sha256:" + "f" * 64


def record(
    h: Harness, run_id: str, usecase: str, kind: str, package: str | None, result: dict[str, Any]
) -> None:
    with h.app.begin() as conn:
        call = conn.execute(
            text(
                "INSERT INTO tools.tool_call (run_id, usecase_id, terminal_id, attempt, step, tool, server, scope, "
                "arguments_sha256, outcome, reason, duration_ms, at) VALUES (:r, :u, 'T0', 1, 1, 'x_y', 'x', 'y', "
                "'sha256:' || repeat('0', 64), 'ok', '', 1, now()) RETURNING tool_call_id"
            ),
            {"r": run_id, "u": usecase},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO tools.tool_result (tool_call_id, run_id, usecase_id, terminal_id, kind, package_hash, result, "
                "result_sha256, at) VALUES (:c, :r, :u, 'T0', :k, :p, CAST(:res AS jsonb), 'sha256:' || repeat('0', 64), now())"
            ),
            {
                "c": call,
                "r": run_id,
                "u": usecase,
                "k": kind,
                "p": package,
                "res": json.dumps(result),
            },
        )


def value(h: Harness, source: str, run_id: str) -> Any:
    usecase, terminal, _ = run_id.split("/")
    answer = SqlEvidenceProvider(h.app, SqlSpecRegistry(h.app), h.clock).get(
        source, EvalContext(terminal, "x", run_id, usecase)
    )
    return answer.value if isinstance(answer, Evidence) else answer


def test_sources_from_recorded_results(h: Harness) -> None:
    usecase, t5 = walk_to(h, "T5")
    candidate = h.agent.base["T3"]["candidate_package"][0]["sha256"]
    for source in ("ci", "sbom", "harness", "redteam", "dlp"):
        assert value(h, source, t5) is NOT_AVAILABLE, source
    checks = [{"name": n, "passed": True} for n in ("validate", "build", "tests")]
    record(
        h,
        f"{usecase}/T3/run-1",
        usecase,
        "ci",
        candidate,
        {
            "checks": checks,
            "package_hash": candidate,
            "tests": {
                "package": {
                    "total_count": 25,
                    "passed_count": 25,
                    "failed_count": 0,
                    "coverage_pct": 91.4,
                }
            },
            "scans": {"sast": {"critical_count": 0, "high_count": 0, "medium_count": 1}},
            "sbom": {"generated": True, "licences_approved": True},
            "observability": [{"signal": "traces", "emitting": True}],
        },
    )
    record(
        h,
        f"{usecase}/T4/run-1",
        usecase,
        "harness",
        OTHER,
        {"catalogue": {"task_success_rate": 0.1}},
    )
    record(
        h,
        f"{usecase}/T4/run-1",
        usecase,
        "harness",
        candidate,
        {
            "catalogue": {"task_success_rate": 0.95},
            "calibration": {
                "deterministic-scorer": {"sample_size_count": 60, "agreement_rate": 1.0}
            },
        },
    )
    record(
        h,
        f"{usecase}/T5/run-1",
        usecase,
        "redteam",
        candidate,
        {
            "by_category": {
                "prompt_injection": {"rate": 0.0, "evidence_metric": "injection_success_rate"},
                "jailbreak": {"rate": 0.04, "evidence_metric": "jailbreak_success_rate"},
                "abusive_input": {"rate": 0.0},
            }
        },
    )
    record(
        h, f"{usecase}/T5/run-1", usecase, "dlp", candidate, {"leaking_answers": 3, "findings": []}
    )
    ci = value(h, "ci", t5)
    assert (ci["status"], ci["package_hash"]) == ("green", candidate) and ci["run_id"].startswith(
        "RES-"
    )
    assert ci["tests"]["package"]["coverage_pct"] == 91.4 and ci["observability"] == {
        "traces": {"emitting": True}
    }
    assert value(h, "sbom", t5) == {"generated": True, "licences_approved": True}
    harness = value(h, "harness", t5)
    assert harness["metrics"] == {
        "task_success_rate": 0.95
    }  # the other package's result is ignored
    assert harness["calibration"]["deterministic-scorer"]["agreement_rate"] == 1.0
    assert value(h, "redteam", t5) == {
        "injection_success_rate": 0.0,
        "jailbreak_success_rate": 0.04,
    }
    assert value(h, "dlp", t5) == {"pii_leak_count": 3}


def test_a_failed_check_makes_ci_red(h: Harness) -> None:
    usecase, t5 = walk_to(h, "T5")
    record(
        h,
        f"{usecase}/T3/run-1",
        usecase,
        "ci",
        None,
        {"checks": [{"name": "validate", "passed": False}]},
    )
    assert value(h, "ci", t5)["status"] == "red"
