"""013 T006 (US1; FR-001, FR-002): the journey of a walk with a clarification, a rework routed to
another terminal, an exception with a waiver, an escalation and a drift re-entry."""

from adlc.dashboard.service import DashboardService
from tests.integration.dashboard.walk import walked
from tests.support.orchestration import harness
from tests.support.pg import PlatformDatabase


def _arrows(journey: dict, kind: str) -> list[dict]:
    return [a for a in journey["arrows"] if a["kind"] == kind]


def test_journey_shows_every_run_and_arrow(orch_template: PlatformDatabase) -> None:
    with walked(orch_template) as w:
        journey = DashboardService(w.h.orch.runs).journey(w.usecase)
        lanes = {lane["terminal_id"]: lane for lane in journey["lanes"]}
        assert list(lanes) == [f"T{n}" for n in range(10)]
        assert [b["run_number"] for b in lanes["T3"]["runs"]] == [1, 2]
        assert [b["run_number"] for b in lanes["T2"]["runs"]] == [1, 2]  # re-entry opened run 2

        (reroute,) = _arrows(journey, "reroute")
        assert (reroute["from_run"], reroute["to_run"]) == (
            f"{w.usecase}/T4/run-1",
            f"{w.usecase}/T3/run-2",
        )
        assert reroute["cause"] == {
            "root_cause": "implementation",
            "comment": "routing rules miss a team",
            "decision": "rework",
        }
        assert reroute["actor"] == "qa_eval_lead-person"

        (exception,) = _arrows(journey, "exception")
        assert (
            exception["cause"]["waiver_id"] == "WVR-0001"
            and exception["cause"]["expiry"] == "2099-12-31"
        )
        (event,) = _arrows(journey, "event")
        assert event["cause"]["monitor_id"] == "MON-04" and event["to_run"].endswith("/T9/run-1")
        (reentry,) = _arrows(journey, "re-entry")
        assert reentry["from_run"].endswith("/T9/run-1") and reentry["to_run"].endswith("/T2/run-2")

        panel = journey["panel"]
        assert [e["terminal_id"] for e in panel["escalations"]] == ["T6"]
        assert [x["waiver_id"] for x in panel["exceptions"]] == ["WVR-0001"]
        open_t2 = lanes["T2"]["runs"][-1]
        assert open_t2["closed_at"] is None and open_t2["owner"]  # who it waits for
        t2_first = lanes["T2"]["runs"][0]
        assert t2_first["time_split"]["clarification"] == 600.0


def test_a_new_use_case_shows_t0_waiting(orch_template: PlatformDatabase) -> None:
    with harness(orch_template) as h:
        usecase = h.submit()
        journey = DashboardService(h.orch.runs).journey(usecase)
        t0 = journey["lanes"][0]
        assert t0["terminal_id"] == "T0" and len(t0["runs"]) == 1
        assert journey["arrows"] == []
