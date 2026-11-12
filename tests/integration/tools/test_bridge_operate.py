"""T033 (US5; FR-019 to FR-021, SC-007, SC-008): T8 reads metrics, masked traces and feedback; a
monitor T6 configured fires when routing accuracy drops, from the background evaluation."""

import json
import time
from typing import Any

from adlc.agents.tools import ToolOutput

from .conftest import Tools


def output(reply: object) -> dict[str, Any]:
    assert isinstance(reply, ToolOutput), reply
    loaded: dict[str, Any] = json.loads(reply.text)
    return loaded


def test_metrics_traces_and_feedback(tools: Tools) -> None:
    t8 = tools.gate("T8", "observability_metrics", "observability_traces", "feedback_read")
    metrics = output(t8("observability_metrics", {"window_s": 120}))
    assert metrics["metrics"]["routing_accuracy"] == 0.97 and metrics["window_s"] == 60
    traces = output(t8("observability_traces", {"minutes": 5}))
    assert [s["request_id"] for s in traces["spans"]] == ["INC-1", "INC-2"]
    text = json.dumps(traces)
    assert "secret@example.com" not in text and "description" not in text and "reason" not in text
    one = output(t8("observability_traces", {"request_id": "INC-2"}))
    assert [s["request_id"] for s in one["spans"]] == ["INC-2"]
    feedback = output(t8("feedback_read", {"limit": 5}))
    assert feedback["synthetic"] is True


def test_a_monitor_fires_in_the_background_when_accuracy_drops(tools: Tools) -> None:
    t6 = tools.gate("T6", "monitoring_configure")
    made = output(
        t6(
            "monitoring_configure",
            {"metric": "routing_accuracy", "operator": "<", "threshold": 0.8, "window_s": 120},
        )
    )
    t8 = tools.gate("T8", "monitoring_read")
    assert output(t8("monitoring_read"))["monitors"][0]["firing"] is False
    tools.pilot.traffic["routing_accuracy"] = 0.51  # the model swap's effect
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:  # the bridge evaluates every 0.2 s in these tests
        events = [
            r
            for r in (tools.bridge_dir / "records" / "monitors.jsonl").read_text().splitlines()
            if '"fired"' in r
        ]
        if events:
            break
        time.sleep(0.1)
    state = output(t8("monitoring_read"))["monitors"][0]
    assert state["monitor_id"] == made["monitor_id"] and state["firing"] is True
    assert state["events"][0]["value"] == 0.51
