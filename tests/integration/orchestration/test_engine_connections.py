"""T012 (006): agents and the reviewer run with no database connection held (research R-07)."""

from typing import Any

from adlc.orchestration.interfaces import BuildContext, ReviewContext
from adlc.orchestration.stubs import StubAgent, StubReviewer
from tests.support.lifecycle import walk_to
from tests.support.orchestration import harness
from tests.support.pg import PlatformDatabase


class Probe:
    engine: Any = None
    checked_out: list[int] = []  # noqa: RUF012 - test probe


class ProbingAgent(StubAgent):
    def build(self, context: BuildContext):  # type: ignore[no-untyped-def]
        Probe.checked_out.append(Probe.engine.pool.checkedout())
        return super().build(context)


class ProbingReviewer(StubReviewer):
    def review(self, context: ReviewContext):  # type: ignore[no-untyped-def]
        Probe.checked_out.append(Probe.engine.pool.checkedout())
        return super().review(context)


def test_no_connection_held_during_agent_and_review(orch_template: PlatformDatabase) -> None:
    Probe.checked_out = []
    with harness(orch_template, agent=ProbingAgent(), reviewer=ProbingReviewer()) as h:
        Probe.engine = h.orch.runs.engine
        walk_to(h, "T2")
    assert len(Probe.checked_out) >= 4  # T0 and T1: a build and a review each
    assert set(Probe.checked_out) == {0}
