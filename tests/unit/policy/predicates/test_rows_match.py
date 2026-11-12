"""011 T003 (FR-012, research R-07): copied measured values must equal the recorded results."""

from typing import Any

from tests.unit.policy.conftest import Check, fails, passes

CI = {
    "tests": {
        "package": {"total_count": 25, "passed_count": 25, "failed_count": 0, "coverage_pct": 91.4}
    },
    "scans": {"sast": {"critical_count": 0, "high_count": 0, "medium_count": 2}},
}
HARNESS = {"metrics": {"task_success_rate": 0.955, "p95_latency_ms": 6.8}}


def sources(t3: dict[str, Any] | None = None, t4: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"T3": t3 or {}, "T4": t4 or {}, "ci": CI, "harness": HARNESS}


def test_rows_match_compares_every_recorded_column(check: Check) -> None:
    good = {
        "test_results": [
            {
                "suite": "package",
                "total_count": 25,
                "passed_count": 25,
                "failed_count": 0,
                "coverage_pct": 91.4004,
            }
        ]
    }
    passes(check('rows_match(T3.test_results, "suite", ci.tests)', sources(good)))
    copied = {
        "test_results": [
            {
                "suite": "package",
                "total_count": 25,
                "passed_count": 25,
                "failed_count": 0,
                "coverage_pct": 95,
            }
        ]
    }
    fails(
        check('rows_match(T3.test_results, "suite", ci.tests)', sources(copied)),
        "row 1: package coverage_pct 95",
    )
    invented = {
        "test_results": [
            {
                "suite": "unit",
                "total_count": 400,
                "passed_count": 400,
                "failed_count": 0,
                "coverage_pct": 99,
            }
        ]
    }
    fails(
        check('rows_match(T3.test_results, "suite", ci.tests)', sources(invented)),
        "row 1: no recorded result for unit",
    )
    scans = {
        "security_build_checks": [
            {
                "scan": "sast",
                "tool": "bandit",
                "critical_count": 0,
                "high_count": 0,
                "medium_count": 2,
                "status": "pass",
            }
        ]
    }
    passes(check('rows_match(T3.security_build_checks, "scan", ci.scans)', sources(scans)))


def test_rows_match_value_and_not_measured(check: Check) -> None:
    rows = {
        "quality_vs_threshold": [
            {"metric": "task_success_rate", "threshold": 0.9, "actual": 0.955, "result": "pass"},
            {
                "metric": "groundedness_rate",
                "threshold": 0.9,
                "actual": "not measured",
                "result": "fail",
            },
        ]
    }
    passes(
        check(
            'rows_match_value(T4.quality_vs_threshold, "metric", "actual", harness.metrics)',
            sources(t4=rows),
        )
    )
    rows["quality_vs_threshold"][0]["actual"] = 0.97
    fails(
        check(
            'rows_match_value(T4.quality_vs_threshold, "metric", "actual", harness.metrics)',
            sources(t4=rows),
        ),
        "row 1: task_success_rate actual 0.97",
    )
    unmeasured = {
        "quality_vs_threshold": [
            {"metric": "groundedness_rate", "threshold": 0.9, "actual": 0.99, "result": "pass"}
        ]
    }
    fails(
        check(
            'rows_match_value(T4.quality_vs_threshold, "metric", "actual", harness.metrics)',
            sources(t4=unmeasured),
        ),
        "row 1: groundedness_rate was not measured",
    )


def test_missing_evidence_fails_closed(check: Check) -> None:
    result = check(
        'rows_match(T3.test_results, "suite", ci.tests)',
        {"T3": {"test_results": [{"suite": "package"}]}},
    )
    assert not result.passed
