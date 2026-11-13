"""T022: release, rollout and operations predicates."""

from typing import Any

from tests.unit.policy.conftest import Check, fails, passes

HASH = "sha256:" + "a" * 64
T: dict[str, Any] = {
    "T1": {
        "kpis": [{"kpi": "csat", "target": 4.5}],
        "rai_thresholds": [{"metric": "toxicity", "operator": "<=", "threshold": 0.01}],
        "non_functional_requirements": [{"category": "availability", "target": 99.5}],
    },
    "T2": {
        "observability_design": [{"signal": "latency"}],
        "token_budget": [{"max_cost_usd": 0.05}],
    },
    "T3": {"candidate_package": [{"sha256": HASH}]},
    "T4": {"eval_baseline": {"value": 0.9, "tolerance": 0.02}},
    "T6": {
        "monitoring_readiness": [
            {"signal": "csat", "alert_threshold": "4.0"},
            {"signal": "latency", "alert_threshold": "2s"},
        ],
        "gaps": [{"signal": "csat", "alert_threshold": ""}],
        "release_authorisation": [{"decision": "go"}, {"decision": "go"}],
        "split": [{"decision": "go"}, {"decision": "no-go"}],
        "deployment_package": [{"sha256": HASH}],
    },
    "T7": {
        "stage_metrics": [
            {"stage": "shadow", "metric": "acc", "result": "pass"},
            {"stage": "canary", "metric": "err", "result": "pass"},
        ],
        "bad_stage": [
            {"stage": "canary", "metric": "err", "result": "breach"},
            {"stage": "shadow", "metric": "acc", "result": "fail"},
        ],
        "deployment_log": [{"stage": "rollback", "result": "failed"}],
        "good_log": [{"stage": "rollback", "result": "success"}],
        "hypercare_log": [{"severity": "sev2", "closed": ""}],
    },
    "T8": {
        "operating_health_report": [{"metric": "acc", "status": "ok"}],
        "regressed": [{"metric": "acc", "status": "fail"}],
        "incident_problem_log": [{"severity": "sev1"}, {"severity": "sev1"}],
        "one": [{"severity": "sev1"}],
    },
    "env": {"test": {"deployed_hash": HASH}, "stale": {"deployed_hash": "sha256:" + "b" * 64}},
    "change": {
        "window": {"start": "2026-11-10T00:00:00+00:00", "end": "2026-11-11T00:00:00+00:00"},
        "past": {"start": "2026-01-01T00:00:00+00:00", "end": "2026-01-02T00:00:00+00:00"},
    },
    "telemetry": {
        "monitors": {"safety": True, "cost": "yes"},
        "toxicity": 0.03,
        "toxicity_ok": 0.005,
        "availability_pct": 99.1,
        "online_eval_score": 0.85,
        "cost_series": [
            {"at": "2026-11-05T00:00:00+00:00", "value": 0.07},
            {"at": "2026-11-09T00:00:00+00:00", "value": 0.08},
        ],
        "kpi_values": {"csat": [4.1, 4.2, 4.0]},
    },
}


def test_alerts(check: Check) -> None:
    passes(check("alerts_cover(T6.monitoring_readiness, T1.kpis, T2.observability_design)", T))
    fails(
        check("alerts_cover(T6.gaps, T1.kpis, T2.observability_design)", T),
        "T6.gaps: no alert for 'csat'",
    )


def test_go_no_go(check: Check) -> None:
    passes(check("go_no_go_disputed(T6.split)", T))
    fails(check("go_no_go_disputed(T6.release_authorisation)", T), "decisions agree")


def test_window(check: Check) -> None:
    passes(check("within_window(change.window)", T))
    fails(check("within_window(change.past)", T), "is outside")


def test_hashes(check: Check) -> None:
    passes(check("hash_matches(env.test, T3.candidate_package)", T))
    passes(check("hash_matches(T6.deployment_package, T3.candidate_package)", T))
    fails(check("hash_matches(env.stale, T3.candidate_package)", T), "does not match")


def test_stages(check: Check) -> None:
    passes(check('within_baseline_tolerance(T7.stage_metrics, T4.eval_baseline, "shadow")', T))
    fails(
        check('within_baseline_tolerance(T7.bad_stage, T4.eval_baseline, "shadow")', T),
        "T7.bad_stage row 2: acc result is 'fail'",
    )
    passes(check('no_breach_in_stage(T7.stage_metrics, "canary")', T))
    fails(
        check('no_breach_in_stage(T7.bad_stage, "canary")', T), "T7.bad_stage row 1: err breached"
    )


def test_rollback_and_incidents(check: Check) -> None:
    passes(check("rollback_failed(T7.deployment_log)", T))
    fails(check("rollback_failed(T7.good_log)", T), "no failed rollback")
    passes(check('open_incident(T7.hypercare_log, ["sev1", "sev2"])', T))
    fails(check('open_incident(T7.hypercare_log, ["sev1"])', T), "no open incident")
    passes(check("repeated_sev1(T8.incident_problem_log)", T))
    fails(check("repeated_sev1(T8.one)", T), "1 sev1 incident(s)")


def test_monitor_thresholds(check: Check) -> None:
    passes(check('exceeds_threshold(telemetry.toxicity, T1.rai_thresholds, "toxicity")', T))
    fails(
        check('exceeds_threshold(telemetry.toxicity_ok, T1.rai_thresholds, "toxicity")', T),
        "toxicity 0.005 meets <= 0.01",
    )
    passes(
        check(
            'below_nfr(telemetry.availability_pct, T1.non_functional_requirements, "availability")',
            T,
        )
    )
    fails(
        check(
            "below_nfr(T1.non_functional_requirements.target, "
            'T1.non_functional_requirements, "availability")',
            T,
        ),
        "is not below",
    )
    passes(check("below_baseline(telemetry.online_eval_score, T4.eval_baseline)", T))
    fails(check("below_baseline(T4.eval_baseline.value, T4.eval_baseline)", T), "is not below")
    # 012 R-09: the built baseline is a one-row table
    built = {
        **T,
        "T4": {**T["T4"], "eval_baseline": [{"metric": "m", "value": 0.9, "tolerance": 0.05}]},
    }
    built["telemetry"] = {**T["telemetry"], "online_eval_score": 0.8}
    passes(check("below_baseline(telemetry.online_eval_score, T4.eval_baseline)", built))
    built["telemetry"] = {**T["telemetry"], "online_eval_score": 0.86}
    fails(
        check("below_baseline(telemetry.online_eval_score, T4.eval_baseline)", built),
        "is not below",
    )
    passes(check('above_budget_for(telemetry.cost_series, T2.token_budget, "7d")', T))
    fails(
        check(
            'above_budget_for(telemetry.cost_series, T2.token_budget, "30d")',
            {
                **T,
                "telemetry": {
                    **T["telemetry"],
                    "cost_series": [{"at": "2026-11-09T00:00:00+00:00", "value": 0.01}],
                },
            },
        ),
        "is not above",
    )
    passes(check("kpi_below_target_for(T1.kpis, telemetry.kpi_values, 3)", T))
    fails(
        check("kpi_below_target_for(T1.kpis, telemetry.kpi_values, 4)", T),
        "no KPI below target for 4 reviews",
    )


def test_monitors_and_regression(check: Check) -> None:
    passes(check("all_monitors_reporting()", T))
    fails(
        check(
            "all_monitors_reporting()",
            {"telemetry": {"monitors": {"safety": True, "drift": False}}},
        ),
        "monitors not reporting: drift",
    )
    fails(check("all_monitors_reporting()", {}), "evidence not available: telemetry")
    passes(check("regression_within_baseline(T8.operating_health_report, T4.eval_baseline)", T))
    fails(
        check("regression_within_baseline(T8.regressed, T4.eval_baseline)", T),
        "T8.regressed row 1: acc status is 'fail'",
    )
