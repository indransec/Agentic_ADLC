"""Rehearsed replies of the T9 agent (feature 014, research R-02; see ``common``)."""

import json
from typing import Any

from demo.rehearsed.common import Messages, all_outputs, tool


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
