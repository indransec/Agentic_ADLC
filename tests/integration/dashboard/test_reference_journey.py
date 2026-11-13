"""013 T021 (SC-001): after the reference replay to T9, the journey shows the T5 exception and the
T8 drift event into T9 as arrows with their causes."""

from pathlib import Path

from adlc.agents.replay import UseCaseResult
from adlc.dashboard.service import DashboardService
from tests.scenario.test_reference_replay_t6_t9 import replay_to_t9
from tests.support.fake_pilot import FakePilot
from tests.support.orchestration import Harness
from tests.support.pg import PlatformDatabase


def _journey_arrows(h: Harness, result: UseCaseResult, fake: FakePilot) -> None:
    assert result.outcome == "completed", result.outcome
    journey = DashboardService(h.orch.runs).journey(result.usecase_id)
    kinds = {
        (a["kind"], a["from_run"].split("/")[1], a["to_run"].split("/")[1])
        for a in journey["arrows"]
    }
    assert {("exception", "T5", "T6"), ("event", "T8", "T9")} <= kinds
    exception = next(a for a in journey["arrows"] if a["kind"] == "exception")
    assert exception["cause"]["waiver_id"] and exception["cause"]["expiry"] == "2099-12-31"
    event = next(a for a in journey["arrows"] if a["kind"] == "event")
    assert event["cause"]["monitor_id"] == "MON-04" and event["cause"]["measured"]


def test_reference_journey_arrows(orch_template: PlatformDatabase, tmp_path: Path) -> None:
    replay_to_t9(orch_template, tmp_path, _journey_arrows)
