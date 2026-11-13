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
