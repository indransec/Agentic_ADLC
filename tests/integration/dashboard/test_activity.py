"""013 T010 (US2; FR-003): the activity feed, newest first, filterable."""

from adlc.dashboard.service import DashboardService
from tests.integration.dashboard.walk import walked
from tests.support.pg import PlatformDatabase


def test_feed_order_and_filters(orch_template: PlatformDatabase) -> None:
    with walked(orch_template) as w:
        dashboard = DashboardService(w.h.orch.runs)
        feed = dashboard.activity(usecase_id=w.usecase)
        assert feed and [e["at"] for e in feed] == sorted((e["at"] for e in feed), reverse=True)
        assert {
            "at",
            "run_id",
            "terminal_id",
            "actor_type",
            "actor",
            "step",
            "outcome",
            "seconds",
        } <= set(feed[0])
        people = dashboard.activity(usecase_id=w.usecase, actor_type="human")
        assert people and all(e["actor_type"] == "human" for e in people)
        assert any(e["step"] == "clarification" for e in people)  # the answer
        t4 = dashboard.activity(usecase_id=w.usecase, terminal_id="T4", step="sign_off")
        assert t4 and all(e["terminal_id"] == "T4" and e["step"] == "sign_off" for e in t4)
        assert {e["run_id"] for e in t4} == {f"{w.usecase}/T4/run-1", f"{w.usecase}/T4/run-2"}
        assert len(dashboard.activity(limit=3)) == 3
        assert len(dashboard.activity(limit=10_000)) <= 1000
