"""Rehearsed replies of the T8 agent (feature 014, research R-02; see ``common``)."""

import copy
import json
from typing import Any

from demo.rehearsed.common import SYN, Messages, all_outputs, tool


class Operations:
    """T8: one review period from the recorded reading; the monitors' fired events are listed as
    raised; ``propose`` adds an event the agent proposes for a person to confirm."""

    METRICS = (
        ("routing_accuracy", 0.85, ">="),
        ("latency_p95_ms", 2000, "<="),
        ("cost", 10.0, "<="),
        ("tokens", 10_000_000, "<="),
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
