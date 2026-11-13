"""014 T013 (D-8): the dashboard shows the demo's progression, reroutes, activity, time, reworks,
clarifications and escalations."""

from pathlib import Path
from typing import Any

from adlc.dashboard.service import DashboardService
from tests.scenario.demo_run import demo_run
from tests.support.pg import PlatformDatabase


def test_d8_dashboard_reflects_the_demo(orch_template: PlatformDatabase, tmp_path: Path) -> None:
    with demo_run(orch_template, tmp_path) as d:
        dashboard = DashboardService(d.h.orch.runs)
        journey = dashboard.journey(d.main)
        kinds = {a["kind"] for a in journey["arrows"]}
        assert {"rework", "reroute", "exception", "event", "re-entry"} <= kinds, kinds
        assert [lane["terminal_id"] for lane in journey["lanes"]] == [f"T{n}" for n in range(10)]
        kpis: dict[str, Any] = {k["id"]: k for k in dashboard.kpis(d.main)["kpis"]}
        assert kpis["reworks"]["value"] == 2  # T1 (requirement) and T4 (implementation)
        assert (
            kpis["clarifications"]["value"] == 1 and kpis["clarification_wait"]["value"] is not None
        )
        assert kpis["escalations"]["value"] >= 1  # T5's kill-switch gap
        actors = {e["actor_type"] for e in dashboard.activity(usecase_id=d.main, limit=1000)}
        assert {"agent", "reviewer", "human", "orchestrator"} <= actors, actors
        escalated = dashboard.kpis(d.report.usecases["escalation"])["kpis"]
        assert (
            next(k for k in escalated if k["id"] == "escalations")["detail"][0]["trigger"]
            == "rework_limit"
        )
