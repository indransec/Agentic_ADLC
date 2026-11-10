"""T021: evaluation and assurance predicates."""

from typing import Any

import pytest

from tests.unit.policy.conftest import Check, fails, passes

T: dict[str, Any] = {
    "T1": {
        "eval_thresholds": [
            {"metric": "accuracy", "operator": ">=", "threshold": "0.9"},
            {"metric": "hallucination", "operator": "<=", "threshold": 0.02},
        ],
        "non_functional_requirements": [{"category": "latency", "target": 2000}],
    },
    "T2": {"token_budget": [{"max_cost_usd": 0.05}]},
    "T4": {
        "quality_vs_threshold": [
            {"metric": "accuracy", "actual": 0.93},
            {"metric": "hallucination", "actual": "0.01"},
        ],
        "weak": [
            {"metric": "accuracy", "actual": 0.8},
            {"metric": "hallucination", "actual": 0.01},
        ],
        "missing": [{"metric": "accuracy", "actual": 0.95}],
        "misses": [{"result": "fail", "severity": "minor"}],
        "critical_miss": [{"result": "fail", "critical": True}],
        "cost_latency": [
            {"measure": "cost_per_task", "actual": 0.03},
            {"measure": "p95_latency_ms", "actual": 1500},
        ],
        "slow": [
            {"measure": "p95_latency_ms", "actual": 2500},
            {"measure": "cost_per_task", "actual": 0.09},
        ],
        "judge_calibration": [{"judge": "j", "agreement_rate": 0.9}],
        "disputed": [{"judge": "j", "disputed": "yes"}],
    },
    "T5": {
        "resilience_verification": [
            {"scenario": "kill_switch", "result": "pass"},
            {"scenario": "fallback", "result": "fail"},
        ],
        "threat_model_results": [
            {"residual_risk": "critical", "result": "mitigated"},
            {"residual_risk": "low", "result": "open"},
        ],
        "open_threat": [{"residual_risk": "high", "result": "open"}],
        "assurance_attestation": [{"decision": "approve"}, {"decision": "Approve"}],
        "split": [{"decision": "approve"}, {"decision": "reject"}],
        "residual_risk_register": [{"decision": "accept"}],
        "unacceptable": [{"decision": "unacceptable"}],
    },
}


def test_metrics(check: Check) -> None:
    passes(check("all_metrics_meet_thresholds(T4.quality_vs_threshold, T1.eval_thresholds)", T))
    fails(
        check("all_metrics_meet_thresholds(T4.weak, T1.eval_thresholds)", T),
        "accuracy 0.8 does not meet >= 0.9",
    )
    fails(
        check("all_metrics_meet_thresholds(T4.missing, T1.eval_thresholds)", T),
        "no result for hallucination",
    )


@pytest.mark.parametrize(
    ("op", "ok"), [(">=", True), (">", True), ("<=", False), ("<", False), ("==", False)]
)
def test_each_operator(check: Check, op: str, ok: bool) -> None:
    sources = {
        "T1": {"t": [{"metric": "m", "operator": op, "threshold": 1}]},
        "T4": {"r": [{"metric": "m", "actual": 2}]},
    }
    result = check("all_metrics_meet_thresholds(T4.r, T1.t)", sources)
    assert result.passed is ok


def test_critical_misses(check: Check) -> None:
    passes(check("no_critical_threshold_missed(T4.misses, T4.quality_vs_threshold)", T))
    fails(
        check("no_critical_threshold_missed(T4.critical_miss, T4.misses)", T),
        "T4.critical_miss row 1: critical threshold missed",
    )


def test_cost_and_latency(check: Check) -> None:
    passes(check("cost_within_budget(T4.cost_latency, T2.token_budget)", T))
    fails(
        check("cost_within_budget(T4.slow, T2.token_budget)", T),
        "cost 0.09 is above the budget 0.05",
    )
    passes(check("latency_within_nfr(T4.cost_latency, T1.non_functional_requirements)", T))
    fails(
        check("latency_within_nfr(T4.slow, T1.non_functional_requirements)", T),
        "latency 2500 is above the NFR 2000.0",
    )


def test_judge_disputed(check: Check) -> None:
    passes(check("judge_disputed(T4.disputed)", T))
    fails(check("judge_disputed(T4.judge_calibration)", T), "no dispute recorded")


def test_scenarios_and_threats(check: Check) -> None:
    passes(check('scenario_passed(T5.resilience_verification, "kill_switch")', T))
    fails(
        check('scenario_passed(T5.resilience_verification, "fallback")', T),
        "fallback result is 'fail'",
    )
    passes(check("no_unmitigated_critical(T5.threat_model_results)", T))
    fails(check("no_unmitigated_critical(T5.open_threat)", T), "row 1: high risk is not mitigated")


def test_assurance(check: Check) -> None:
    passes(check("assurance_disagreement(T5.split)", T))
    fails(check("assurance_disagreement(T5.assurance_attestation)", T), "decisions agree")
    passes(check("unacceptable_residual_risk(T5.unacceptable)", T))
    fails(
        check("unacceptable_residual_risk(T5.residual_risk_register)", T),
        "no residual risk rated unacceptable",
    )
