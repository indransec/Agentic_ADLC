"""013 T015 (US4; FR-005): a run's step timeline with its model and tool calls."""

from pathlib import Path

from adlc.dashboard.service import DashboardService
from tests.integration.agents.test_t7_agent import to_t7
from tests.support.acting import acting
from tests.support.acting_scripts import Deployment
from tests.support.fake_pilot import FakePilot, with_candidate
from tests.support.pg import PlatformDatabase

AGENT = "t7-deployment-agent"


def test_timeline_of_an_acting_run(orch_template: PlatformDatabase, tmp_path: Path) -> None:
    fake = with_candidate(FakePilot(), "test")
    with acting(orch_template, {AGENT: Deployment().script()}, (AGENT,), tmp_path, fake) as a:
        _, run = to_t7(a.h, "low")
        a.h.drain()
        timeline = DashboardService(a.h.orch.runs).run_timeline(run.run_id)
        steps = [e["step"] for e in timeline["activity"]]
        assert "build" in steps and all(e["seconds"] >= 0 for e in timeline["activity"])
        build = next(x for x in timeline["attempts"] if x["kind"] == "build")
        assert build["model_calls"] and all(
            c["tokens_in"] >= 0 and c["model"] for c in build["model_calls"]
        )
        tools = [c["tool"] for c in build["tool_calls"]]
        assert tools[:2] == ["cd_status", "cd_deploy"] and "agent_registry_write" in tools
