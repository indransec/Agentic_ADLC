"""Rehearsed replies of the T7 agent (feature 014, research R-02; see ``common``)."""

import json
from collections.abc import Sequence
from typing import Any

from demo.rehearsed.common import Messages, Reply, all_outputs, rows_of, tool


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
