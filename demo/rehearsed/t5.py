"""Rehearsed replies of the T5 agent (feature 014, research R-02; see ``common``)."""

import copy
import json
from typing import Any

from demo.rehearsed.common import SYN, Messages, all_outputs, rows_of, tool


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
