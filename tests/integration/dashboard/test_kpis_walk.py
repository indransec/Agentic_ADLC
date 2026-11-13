"""013 T014 (US3; SC-002): the KPIs of the scripted walk equal the hand-computed values."""

from typing import Any

from sqlalchemy import text

from adlc.dashboard.service import DashboardService
from tests.integration.dashboard.walk import walked
from tests.support.pg import PlatformDatabase


def test_kpis_of_the_walk(orch_template: PlatformDatabase) -> None:
    with walked(orch_template) as w:
        found: dict[str, Any] = {
            k["id"]: k for k in DashboardService(w.h.orch.runs).kpis(w.usecase)["kpis"]
        }
        assert found["reworks"]["value"] == 1
        assert found["reworks"]["per_terminal"] == {"T4": {"implementation": 1}}
        assert found["clarifications"]["value"] == 1
        assert list(found["clarifications"]["per_terminal"]) == ["T2"]
        assert found["clarification_wait"]["value"] == 600.0  # answered after 10 minutes
        assert found["escalations"]["value"] == 1
        assert found["escalations"]["detail"][0]["terminal_id"] == "T6"
        assert found["escalations"]["detail"][0]["trigger"] == "retry_limit"
        # first runs closed: T0-T9 except T2 run 2 (open); first runs of T4 (rework) and T5
        # (exception counts as signed) -> every first run but T4's passed or excepted
        firsts = w.h.sql(
            "SELECT count(*) FROM run.terminal_run WHERE usecase_id = :u AND run_number = 1 "
            "AND state = 'closed'",
            u=w.usecase,
        )[0][0]
        assert found["first_pass_yield"]["value"] == (firsts - 1) / firsts
        assert found["elapsed"]["value"] > 0
        with w.h.app.connect() as conn:
            passed = conn.execute(
                text(
                    "SELECT count(*) FILTER (WHERE passed), count(*) FROM (SELECT DISTINCT ON "
                    "(run_id, check_id) run_id, check_id, passed FROM run.policy_decision "
                    "WHERE usecase_id = :u AND kind = 'evaluate' AND check_id LIKE 'CTL-%' "
                    "AND attempt = 1 ORDER BY run_id, check_id, policy_decision_id) d"
                ),
                {"u": w.usecase},
            ).one()
        assert found["control_first_pass"]["value"] is not None
        assert found["control_first_pass"]["value"] <= 1 and passed[1] > 0
