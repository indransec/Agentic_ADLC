"""Rehearsed replies of the T4 agent (feature 014, research R-02; see ``common``)."""

import json
from typing import Any

from demo.rehearsed.common import REQS, Messages, all_outputs, rows_of, tool


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
