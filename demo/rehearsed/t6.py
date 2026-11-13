"""Rehearsed replies of the T6 agent (feature 014, research R-02; see ``common``)."""

import copy
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from demo.rehearsed.common import SYN, Messages, all_outputs, rows_of, tool


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
