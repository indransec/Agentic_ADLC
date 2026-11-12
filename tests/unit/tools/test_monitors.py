"""T033 (FR-020, SC-007): monitors per use case; one fired event per breach episode with value and
time; re-armed after recovery; unknown metrics and operators refused."""

from pathlib import Path
from typing import Any

import pytest

from adlc.tools.bridge.operate import Monitors
from adlc.tools.bridge.records import Records
from adlc.tools.catalogue import CATALOGUE
from adlc.tools.mcp_app import Call, ToolFailure
from adlc.tools.token import issue


def call(usecase: str = "UC-0001") -> Call:
    claims = issue(
        run_id=f"{usecase}/T6/run-1",
        usecase_id=usecase,
        terminal_id="T6",
        attempt=1,
        scopes=["mcp:monitoring:configure"],
        now=0,
    )
    return Call(CATALOGUE.tools["monitoring_configure"], claims)


def test_fires_once_per_episode_and_rearms(tmp_path: Path) -> None:
    values: dict[str, Any] = {"routing_accuracy": 0.97}
    monitors = Monitors(Records(tmp_path), lambda: {"metrics": dict(values)})
    made = monitors.configure(
        call(), {"metric": "routing_accuracy", "operator": "<", "threshold": 0.8, "window_s": 120}
    )
    assert made == {"monitor_id": "MON-1"}
    monitors.evaluate()
    assert monitors.read("UC-0001")["monitors"][0]["firing"] is False
    values["routing_accuracy"] = 0.55
    for _ in range(3):
        monitors.evaluate()
    state = monitors.read("UC-0001")["monitors"][0]
    assert state["firing"] is True
    assert [(e["kind"], e["value"]) for e in state["events"]] == [("fired", 0.55)]
    assert state["events"][0]["at"]
    values["routing_accuracy"] = 0.95
    monitors.evaluate()
    values["routing_accuracy"] = 0.5
    monitors.evaluate()
    kinds = [e["kind"] for e in monitors.read("UC-0001")["monitors"][0]["events"]]
    assert kinds == ["fired", "recovered", "fired"]
    assert monitors.read("UC-0002") == {"monitors": []}  # per use case


def test_missing_values_are_not_breaches_and_bad_monitors_are_refused(tmp_path: Path) -> None:
    monitors = Monitors(Records(tmp_path), lambda: {"metrics": {"routing_accuracy": None}})
    monitors.configure(
        call(), {"metric": "routing_accuracy", "operator": "<", "threshold": 0.8, "window_s": 60}
    )
    monitors.evaluate()
    assert monitors.read("UC-0001")["monitors"][0]["events"] == []
    for bad in (
        {"metric": "made_up", "operator": "<", "threshold": 1, "window_s": 60},
        {"metric": "routing_accuracy", "operator": "!=", "threshold": 1, "window_s": 60},
        {"metric": "routing_accuracy", "operator": "<", "threshold": "x", "window_s": 60},
    ):
        with pytest.raises(ToolFailure):
            monitors.configure(call(), bad)
