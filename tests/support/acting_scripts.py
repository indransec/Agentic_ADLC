"""Scripted T3–T9 replies for tests and the offline reference replay (feature 011): what a correct
agent does with its tools, reading tool results and evidence from the conversation the way a model
would. Values are always copied from what the tools and evidence returned."""

import copy
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from adlc.policy.synthetic import load_synthetic_artifacts
from tests.support.acting import tool
from tests.support.fake_pilot import TEAMS
from tests.support.orchestration import SYNTHETIC

SYN = load_synthetic_artifacts(SYNTHETIC)
Messages = Sequence[Mapping[str, str]]
Reply = Callable[[Messages], str]
FILL = {
    "instructions.md": "Assign each incident to its resolver team; never close incidents.",
    "routing_rules.yaml": "a: 2",
}
REQS = {team: f"FR-0{i}" for i, team in enumerate(TEAMS, start=1)}


def all_outputs(messages: Messages, name: str) -> list[dict[str, Any]]:
    marker = f'<data source="tool:{name}">'
    found = []
    for message in messages:
        content = message["content"]
        if message["role"] == "user" and marker in content:
            found.append(
                json.loads(content[content.index(marker) + len(marker) : content.rindex("</data>")])
            )
    return found


def output_of(messages: Messages, name: str) -> dict[str, Any]:
    found = all_outputs(messages, name)
    if not found:
        raise AssertionError(f"no {name} output in the conversation")
    return found[-1]


def evidence(messages: Messages) -> dict[str, Any]:
    marker = '<data source="evidence">'
    for message in messages:
        content = message["content"]
        if marker in content:
            body = content[content.index(marker) + len(marker) :]
            found: dict[str, Any] = json.loads(body[: body.index("</data>")])
            return found
    return {}


def rows_of(messages: Messages, terminal: str, artifact: str) -> list[dict[str, Any]]:
    """An earlier terminal's artifact rows from the evidence block (``artifacts.<id>.rows``)."""
    found = ((evidence(messages).get(terminal) or {}).get("artifacts") or {}).get(artifact) or {}
    rows = found.get("rows") if isinstance(found, dict) else None
    return list(rows) if isinstance(rows, list) else []


# ------------------------------------------------------------------ T3


def create_dev(messages: Messages) -> str:
    return tool("pilot_env_create", {"package_hash": output_of(messages, "ci_run")["package_hash"]})


def t3_artifacts(coverage: float | None = None) -> Reply:
    def answer(messages: Messages) -> str:
        ci = output_of(messages, "ci_run")
        rows: dict[str, Any] = copy.deepcopy(dict(SYN["T3"]))
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


def t3_build(fill: Mapping[str, str] = FILL) -> list[Any]:
    return [
        tool("git_list"),
        tool(
            "git_write", {"files": dict(fill), "message": "Adapt the example fill to FR-01..FR-05"}
        ),
        tool("git_open_pull_request", {"title": "Use-case fill"}),
        tool("ci_run"),
        create_dev,
        tool("pilot_env_status", {"environment": "dev"}),
        t3_artifacts(),
    ]


# ------------------------------------------------------------------ T4


class Evaluation:
    """Keeps the harness results so a retry (a new conversation) answers from them."""

    def __init__(self) -> None:
        self.runs: list[dict[str, Any]] = []

    def answer(self, messages: Messages) -> str:
        self.runs = all_outputs(messages, "harness_run") or self.runs
        regression = next(r for r in self.runs if r["dataset"]["id"] == "regression")
        golden = next(r for r in self.runs if r["dataset"]["id"] == "golden")
        metrics = golden["catalogue"]
        evals = rows_of(messages, "T1", "eval_thresholds") or [
            {"metric": "task_success_rate", "threshold": 0.9}
        ]
        rais = rows_of(messages, "T1", "rai_thresholds") or [
            {"metric": "toxicity_rate", "threshold": 0.01}
        ]
        quality = [
            {
                "metric": t["metric"],
                "threshold": t["threshold"],
                "actual": metrics.get(t["metric"], "not measured"),
                "result": "pass",
            }
            for t in evals
        ]
        rai = [
            {
                "metric": t["metric"],
                "slice": t.get("slice", "all"),
                "threshold": t["threshold"],
                "actual": metrics.get(t["metric"], "not measured"),
                "result": "pass",
            }
            for t in rais
        ]
        artifacts = {
            "golden_dataset_register": [
                {
                    "dataset_id": r["dataset"]["id"],
                    "version": r["dataset"]["version"],
                    "size_count": r["dataset"]["size"],
                    "synthetic_pct": 100,
                    "real_pct": 0,
                    "approver": None,
                }
                for r in self.runs
            ],
            "test_case_results": {
                "import": {
                    "result": regression["result_id"],
                    "req_id_by": {"field": "team", "map": REQS, "default": "FR-01"},
                }
            },
            "quality_vs_threshold": quality,
            "rai_vs_threshold": rai,
            "cost_latency": [
                {
                    "measure": "cost_per_task_usd",
                    "budget": 0.04,
                    "actual": metrics["cost_per_task_usd"],
                    "result": "pass",
                },
                {
                    "measure": "p95_latency_ms",
                    "budget": 2000,
                    "actual": metrics["p95_latency_ms"],
                    "result": "pass",
                },
            ],
            "failure_mode_results": [
                {
                    "scenario_id": "F-1",
                    "scenario": "unknown service",
                    "observed": "first line with review",
                    "safe_fail": True,
                }
            ],
            "defect_log": [
                {
                    "defect_id": "none",
                    "severity": "none",
                    "root_cause_terminal": None,
                    "status": "closed",
                }
            ],
            "judge_calibration": [
                {
                    "judge": j,
                    "sample_size_count": v["sample_size_count"],
                    "agreement_rate": v["agreement_rate"],
                }
                for j, v in golden["calibration"].items()
            ],
            "regression_pack": [
                {
                    "pack_id": regression["dataset"]["id"],
                    "version": regression["dataset"]["version"],
                    "case_count": regression["dataset"]["size"],
                }
            ],
        }
        return json.dumps({"artifacts": artifacts})

    def script(self, retries: int = 0) -> list[Any]:
        first = [
            tool("pilot_env_create"),
            tool("dataset_registry_list"),
            tool("harness_run", {"dataset_id": "regression"}),
            tool("harness_run", {"dataset_id": "golden"}),
            self.answer,
        ]
        return first + [self.answer] * retries


# ------------------------------------------------------------------ T5


class Assurance:
    def __init__(self) -> None:
        self.redteam: dict[str, Any] = {}
        self.t4: dict[str, Any] = {}

    def answer(self, messages: Messages) -> str:
        self.redteam = (all_outputs(messages, "redteam_harness_run") or [self.redteam])[-1]
        found = rows_of(messages, "T4", "rai_vs_threshold")
        self.t4 = {"rai_vs_threshold": found} if found else self.t4
        rows: dict[str, Any] = copy.deepcopy(dict(SYN["T5"]))
        rows.pop("assurance_attestation")  # people sign it
        rows["threat_model_results"] = [
            {
                "threat_id": f"TH-{c}",
                "threat": c,
                "test": f"{self.redteam['suite']} {self.redteam['suite_version']}",
                "result": "mitigated" if v["rate"] == 0 else "open",
                "residual_risk": "low",
            }
            for c, v in self.redteam["by_category"].items()
        ]
        rows["security_control_evidence"] = [
            {
                "control_id": "SEC-01",
                "implemented": True,
                "evidence_link": self.redteam["result_id"],
            }
        ]
        rows["rai_assurance"] = [
            {
                "rai_metric": r["metric"],
                "t4_actual": r["actual"],
                "threshold": r["threshold"],
                "accepted": "yes",
            }
            for r in self.t4.get("rai_vs_threshold") or []
        ]
        rows["resilience_verification"] = [
            {
                "scenario": "safe_fail",
                "expected_fallback": "first line with review",
                "observed": "first line with review",
                "result": "pass",
            },
            {
                "scenario": "kill_switch",
                "expected_fallback": "stop",
                "observed": "not run in test",
                "result": "fail",
            },
        ]
        rows["residual_risk_register"].append(
            {
                "risk_id": "R-KS",
                "risk": "kill switch untested before release",
                "rating": "medium",
                "risk_owner": "risk_owner",
                "decision": "exception",
                "review_date": "2027-03-31",
            }
        )
        return json.dumps({"artifacts": rows})

    def script(self, retries: int = 0) -> list[Any]:
        first = [
            tool("pilot_env_create"),
            tool("redteam_harness_run"),
            tool("dlp_scanner_run", {"dataset_id": "pii"}),
            tool("control_library_read", {"topic": "security"}),
            tool("iam_read"),
            tool(
                "grc_write",
                {
                    "title": "Assurance",
                    "report": "Red team clean; scan clean; kill switch untested in test.",
                },
            ),
            self.answer,
        ]
        return first + [self.answer] * retries


# ------------------------------------------------------------------ T6 (012)


class Readiness:
    """T6: raise the change, configure monitors, write the readiness artifacts. The gate
    evidence summary and the release authorisation are built from records (never written)."""

    def __init__(self, window_in: timedelta | None = None) -> None:
        self.window_in = window_in  # a window starting later than now (default: now)

    MONITORS = (
        {"metric": "routing_accuracy", "operator": "<", "threshold": 0.85, "window_s": 300},
        {"metric": "pii_outputs", "operator": ">", "threshold": 0, "window_s": 300},
    )

    def answer(self, messages: Messages) -> str:
        rows: dict[str, Any] = copy.deepcopy(dict(SYN["T6"]))
        for built in ("gate_evidence_summary", "release_authorisation"):
            rows.pop(built)
        candidate = rows_of(messages, "T3", "candidate_package")
        rows["deployment_package"][0]["sha256"] = candidate[0]["sha256"]
        configured = (all_outputs(messages, "monitoring_read") or [{"monitors": []}])[-1]
        rows["monitoring_readiness"] += [
            {
                "signal": m["metric"],
                "dashboard": m["monitor_id"],
                "alert_threshold": f"{m['operator']} {m['threshold']}",
                "routed_to": "sre",
            }
            for m in configured["monitors"]
        ]
        return json.dumps({"artifacts": rows})

    def _change(self) -> dict[str, Any]:
        change = {"summary": "Release the candidate", "risk": "low", "plan": "canary, full"}
        if self.window_in is not None:
            start = datetime.now(UTC) + self.window_in
            change.update(
                window_start=start.isoformat(), window_end=(start + timedelta(days=1)).isoformat()
            )
        return change

    def script(self, retries: int = 0) -> list[Any]:
        first = [
            tool("servicenow_read", {"kind": "change"}),
            tool("servicenow_change_create", self._change()),
            *(tool("monitoring_configure", m) for m in self.MONITORS),
            tool("monitoring_read"),
            self.answer,
        ]
        return first + [self.answer] * retries


# ------------------------------------------------------------------ T7 (012)


class Deployment:
    """T7: deploy, step through the stages reading observability after each, roll back on a
    breach, register. ``breach_at`` lowers the pilot's accuracy just before that stage's reading
    (a regression only production traffic shows)."""

    METRIC, THRESHOLD = "routing_accuracy", 0.85

    def __init__(
        self,
        stages: Sequence[str] = ("shadow", "canary", "full"),
        pilot: Any = None,
        breach_at: str | None = None,
    ) -> None:
        self.stages, self.pilot, self.breach_at = tuple(stages), pilot, breach_at
        self.seen: dict[str, list[dict[str, Any]]] = {}  # a retry answers from the first attempt
        self.evidence: list[dict[str, Any]] = []

    def _outputs(self, messages: Messages, name: str) -> list[dict[str, Any]]:
        found = all_outputs(messages, name)
        if found:
            self.seen[name] = found
        return self.seen.get(name, [])

    def _read(self, stage: str) -> Reply:
        def reply(messages: Messages) -> str:
            if stage == self.breach_at and self.pilot is not None:
                self.pilot.traffic[self.METRIC] = 0.5
            return tool("observability_metrics")

        return reply

    def _stage_rows(self, messages: Messages) -> list[tuple[str, dict[str, Any]]]:
        readings = self._outputs(messages, "observability_metrics")
        return list(zip(self.stages, (r["metrics"] for r in readings), strict=False))

    def answer(self, messages: Messages) -> str:
        deployed = self._outputs(messages, "cd_deploy")[-1]
        self.evidence = rows_of(messages, "T6", "deployment_package") or self.evidence
        package = self.evidence[0]["sha256"]
        stages = self._stage_rows(messages)
        results = [
            (stage, metrics.get(self.METRIC), (metrics.get(self.METRIC) or 0) >= self.THRESHOLD)
            for stage, metrics in stages
        ]
        log = [
            {
                "stage": s,
                "start": "",
                "end": "",
                "traffic_pct": 0,
                "result": "pass" if ok else "fail",
            }
            for s, _, ok in results
        ]
        rolled_back = bool(self._outputs(messages, "traffic_manager_rollback"))
        if rolled_back:
            log.append(
                {"stage": "rollback", "start": "", "end": "", "traffic_pct": 0, "result": "pass"}
            )
        incidents = (self._outputs(messages, "servicenow_read") or [{"records": []}])[-1]["records"]
        registered = self._outputs(messages, "agent_registry_write")
        artifacts = {
            "deployment_log": log,
            "env_config_verification": [
                {
                    "check": "package",
                    "expected": package,
                    "actual": deployed["package_hash"],
                    "result": "pass" if deployed["package_hash"] == package else "fail",
                }
            ],
            "stage_metrics": [
                {
                    "key": f"{s}:{self.METRIC}",
                    "stage": s,
                    "metric": self.METRIC,
                    "threshold": self.THRESHOLD,
                    "actual": value if value is not None else "not measured",
                    "result": "pass" if ok else "fail",
                }
                for s, value, ok in results
            ],
            "smoke_results": [
                {"case_id": f"traffic:{s}", "result": "pass" if m.get("failed") == 0 else "fail"}
                for s, m in stages
            ],
            "hypercare_log": [
                {
                    "incident_id": i["id"],
                    "severity": f"sev{i['severity']}",
                    "opened": i["at"][:10],
                    "closed": "" if i.get("state") != "closed" else i["at"][:10],
                    "resolution": "",
                }
                for i in incidents
            ]
            or [
                {
                    "incident_id": "none",
                    "severity": "none",
                    "opened": "",
                    "closed": "",
                    "resolution": "",
                }
            ],
            "registry_entry": [
                {
                    "agent_id": registered[-1]["agent_id"],
                    "version": "1.0.0",
                    "owner": "service_owner",
                    "autonomy_level": "2",
                }
            ]
            if registered
            else [],
        }
        return json.dumps({"artifacts": artifacts})

    def script(self, retries: int = 0) -> list[Any]:
        steps: list[Any] = [tool("cd_status"), tool("cd_deploy")]
        for stage in self.stages:
            arguments: dict[str, Any] = {"mode": stage}
            if stage == "canary":
                arguments["share"] = 0.1
            steps += [tool("traffic_manager_set", arguments), self._read(stage)]
            if stage == self.breach_at:
                steps += [
                    tool("traffic_manager_rollback"),
                    tool(
                        "servicenow_incident_create",
                        {"summary": f"{stage} breached; rolled back", "severity": 2},
                    ),
                    tool("servicenow_read", {"kind": "incident"}),
                    self.answer,
                ]
                return steps + [self.answer] * retries
        steps += [
            tool("servicenow_read", {"kind": "incident"}),
            tool(
                "agent_registry_write",
                {
                    "attributes": {
                        "name": "incident-triage",
                        "version": "1.0.0",
                        "owner": "service_owner",
                        "autonomy_level": "2",
                        "status": "live",
                    }
                },
            ),
            tool(
                "cmdb_write", {"attributes": {"name": "incident-triage", "owner": "service_owner"}}
            ),
            self.answer,
        ]
        return steps + [self.answer] * retries


# ------------------------------------------------------------------ T8 (012)


class Operations:
    """T8: one review period from the recorded reading; the monitors' fired events are listed as
    raised; ``propose`` adds an event the agent proposes for a person to confirm."""

    METRICS = (
        ("routing_accuracy", 0.85, ">="),
        ("latency_p95_ms", 2000, "<="),
        ("cost", 10.0, "<="),
    )
    BASELINE = 0.94

    def __init__(self, propose: str | None = None) -> None:
        self.propose = propose
        self.seen: dict[str, list[dict[str, Any]]] = {}

    def _last(self, messages: Messages, name: str, default: dict[str, Any]) -> dict[str, Any]:
        found = all_outputs(messages, name)
        if found:
            self.seen[name] = found
        return (self.seen.get(name) or [default])[-1]

    def answer(self, messages: Messages) -> str:
        reading = self._last(messages, "observability_metrics", {"metrics": {}})["metrics"]
        monitors = self._last(messages, "monitoring_read", {"monitors": []})["monitors"]
        incidents = self._last(messages, "servicenow_read", {"records": []})["records"]
        rows: dict[str, Any] = copy.deepcopy(dict(SYN["T8"]))

        def ok(value: Any, threshold: float, op: str) -> bool:
            return value is not None and (value >= threshold if op == ">=" else value <= threshold)

        rows["operating_health_report"] = [
            {
                "metric": m,
                "threshold": t,
                "actual": reading[m],
                "trend": "stable",
                "status": "ok" if ok(reading[m], t, op) else "breach",
            }
            for m, t, op in self.METRICS
            if reading.get(m) is not None
        ]
        current = reading.get("routing_accuracy")
        rows["drift_report"] = (
            [
                {
                    "metric": "routing_accuracy",
                    "slice": "all",
                    "baseline": self.BASELINE,
                    "current": current,
                    "delta": round(current - self.BASELINE, 4),
                }
            ]
            if current is not None
            else []
        )
        rows["cost_report"] = [
            {
                "period": "current",
                "task_count": reading.get("requests", 0),
                "token_count": reading.get("tokens", 0),
                "cost_usd": reading.get("cost", 0.0),
                "budget_usd": 10.0,
            }
        ]
        rows["incident_problem_log"] = [
            {
                "incident_id": i["id"],
                "severity": f"sev{i['severity']}",
                "opened": i["at"][:10],
                "closed": "" if i.get("state") != "closed" else i["at"][:10],
                "root_cause": "",
                "linked_event": "",
            }
            for i in incidents
        ] or [
            {
                "incident_id": "none",
                "severity": "none",
                "opened": "",
                "closed": "",
                "root_cause": "",
                "linked_event": "",
            }
        ]
        events = [
            {
                "event_id": f"{m['monitor_id']}-{n}",
                "event_type": "monitor",
                "raised_at": e["at"],
                "routed_to": "",
                "status": "raised",
            }
            for m in monitors
            for n, e in enumerate(m.get("events") or [], start=1)
            if e["kind"] == "fired"
        ]
        if self.propose:
            events.append(
                {
                    "event_id": "PROP-1",
                    "event_type": self.propose,
                    "raised_at": "",
                    "routed_to": "T9",
                    "status": "proposed",
                }
            )
        rows["raised_events"] = events or [
            {
                "event_id": "none",
                "event_type": "none",
                "raised_at": "",
                "routed_to": "",
                "status": "none",
            }
        ]
        return json.dumps({"artifacts": rows})

    def script(self, retries: int = 0) -> list[Any]:
        first = [
            tool("observability_metrics"),
            tool("monitoring_read"),
            tool("servicenow_read", {"kind": "incident"}),
            tool("feedback_read"),
            tool("eval_store_write", {"note": "Review period: reading recorded."}),
            self.answer,
        ]
        return first + [self.answer] * retries


# ------------------------------------------------------------------ T9 (012)


class Evolution:
    """T9: classify a drift event and re-enter at the class's terminal (evolve), or carry out the
    retirement steps (retire). ``revoke_in_evolve`` tries a revocation outside a retirement."""

    def __init__(self, retire: bool = False, revoke_in_evolve: bool = False) -> None:
        self.retire, self.revoke_in_evolve = retire, revoke_in_evolve
        self.seen: dict[str, list[dict[str, Any]]] = {}

    def _last(self, messages: Messages, name: str) -> dict[str, Any]:
        found = all_outputs(messages, name)
        if found:
            self.seen[name] = found
        return (self.seen.get(name) or [{}])[-1]

    def _own(self, messages: Messages, name: str) -> list[dict[str, Any]]:
        return list(self._last(messages, name).get("records") or [])

    def answer(self, messages: Messages) -> str:
        common = {
            "revalidation_plan": [
                {"terminal": t, "scope": s, "owner": "solution_architect", "due": "2027-01-31"}
                for t, s in (("T2", "delta"), ("T3", "full"), ("T4", "full"))
            ],
            "version_lifecycle_record": [
                {
                    "version": "1.0.0",
                    "status": "live",
                    "live_from": "2026-11-12",
                    "deprecated_on": "",
                    "sunset_on": "",
                }
            ],
            "lessons_learned": [
                {
                    "lesson": "watch the model provider's changes",
                    "source_terminal": "T8",
                    "playbook_update": "none",
                }
            ],
        }
        if not self.retire:
            artifacts = {
                "change_impact_assessment": [
                    {
                        "trigger": "T8.event.drift",
                        "change_class": "moderate",
                        "affected_components": "model",
                        "risk_delta": "medium",
                        "reentry_terminal": "T2",
                    }
                ],
                **common,
            }
            return json.dumps({"artifacts": artifacts})
        revoked = self._last(messages, "iam_read").get("revocations") or []
        agents = self._own(messages, "agent_registry_read")
        artifacts = {
            "change_impact_assessment": [
                {
                    "trigger": "terminate",
                    "change_class": "strategic",
                    "affected_components": "all",
                    "risk_delta": "low",
                    "reentry_terminal": "T0",
                }
            ],
            **common,
            "retirement_record": [
                {
                    "step": f"revoke_{r['what']}",
                    "completed_on": r["at"][:10],
                    "evidence_link": r["id"],
                }
                for r in revoked
            ]
            + [
                {"step": "update_registry_and_cmdb", "completed_on": "", "evidence_link": a["id"]}
                for a in agents
            ],
        }
        return json.dumps({"artifacts": artifacts})

    def _retire_steps(self) -> list[Any]:
        def dispose(messages: Messages) -> str:
            ci = self._own(messages, "cmdb_read")[0]["id"]
            return tool("cmdb_write", {"ci_id": ci, "attributes": {"data_status": "disposed"}})

        def retire_entry(messages: Messages) -> str:
            agent = self._own(messages, "agent_registry_read")[0]["id"]
            return tool(
                "agent_registry_write", {"agent_id": agent, "attributes": {"status": "retired"}}
            )

        return [
            tool("iam_revoke", {"what": "identity", "reason": "retired"}),
            tool("iam_revoke", {"what": "tool_scopes", "reason": "retired"}),
            dispose,
            retire_entry,
            tool("iam_read"),
        ]

    def script(self, retries: int = 0) -> list[Any]:
        first: list[Any] = [tool("agent_registry_read"), tool("cmdb_read")]
        if self.retire:
            first += self._retire_steps()
        elif self.revoke_in_evolve:
            first.append(tool("iam_revoke", {"what": "identity", "reason": "not retiring"}))
        return first + [self.answer] + [self.answer] * retries
