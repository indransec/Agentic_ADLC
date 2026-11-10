"""T064: restart safety (SC-004; FR-030, FR-030a, FR-030b; US6/AC1)."""

import contextlib
from collections.abc import Callable
from datetime import timedelta

import pytest
from sqlalchemy import create_engine

from adlc.orchestration.engine import EngineConfig
from adlc.orchestration.interfaces import AgentResult, BuildContext, Clarification
from adlc.orchestration.states import ActorType, Signal, SignalKind
from adlc.orchestration.stubs import StubAgent, StubPolicy, StubReviewer
from adlc.orchestration.worker import Orchestrator, build_orchestrator
from adlc.spec_toolkit.registry import SqlSpecRegistry
from tests.support.lifecycle import walk_to
from tests.support.orchestration import DEADLETTER_ROLE, Harness, harness, person
from tests.support.pg import PlatformDatabase


def restarted(
    h: Harness, agent: StubAgent | None = None, policy: StubPolicy | None = None
) -> Orchestrator:
    """A new orchestrator process over the same database: new engine, no shared memory."""
    engine = create_engine(h.db.app_url)
    return build_orchestrator(
        engine,
        SqlSpecRegistry(engine),
        policy or StubPolicy(),
        agent or StubAgent(),
        StubReviewer(),
        h.clock,
        deadletter_role=DEADLETTER_ROLE,
        config=EngineConfig(),
        worker_id="restarted",
    )


def test_awaiting_sign_off(h: Harness) -> None:
    usecase, t1 = walk_to(h, "T1")
    orch = restarted(h)
    orch.service.decide(person("product_owner"), t1, "pass")
    orch.service.decide(person("business_owner"), t1, "pass")
    orch.drain()
    assert h.active(usecase, "T2").state == "awaiting_sign_off"


def test_blocked(orch_template: PlatformDatabase) -> None:
    policy = StubPolicy({("T1", "PRE-T1-02"): False})
    with harness(orch_template, policy=policy) as h:
        usecase, t1 = walk_to(h, "T1")
        orch = restarted(h, policy=StubPolicy())
        h.clock.advance(timedelta(days=11))
        orch.drain()
        assert h.run(t1).escalation_trigger == "timer"


def test_awaiting_clarification(orch_template: PlatformDatabase) -> None:
    with harness(orch_template, agent=StubAgent({"T2": {1: Clarification(("q",))}})) as h:
        usecase, t2 = walk_to(h, "T2")
        orch = restarted(h)
        orch.service.answer_clarification(person("engineering_lead"), f"{t2}/clar-1", ["a"])
        orch.drain()
        assert h.run(t2).state == "awaiting_sign_off"


def test_escalated(h: Harness) -> None:
    usecase, t1 = walk_to(h, "T1")
    h.clock.advance(timedelta(days=11))
    h.drain()
    orch = restarted(h)
    orch.service.complete_escalation(person("product_owner"), t1, {})
    assert h.run(t1).state == "awaiting_sign_off"


class CrashingAgent(StubAgent):
    """Raises (a crash mid-build) for the first ``crashes`` calls of each terminal."""

    def __init__(self, crashes: int) -> None:
        super().__init__()
        self.crashes = crashes

    def build(self, context: BuildContext) -> AgentResult:
        if self.calls[context.terminal_id] < self.crashes:
            self.calls[context.terminal_id] += 1
            raise RuntimeError("process killed")
        return super().build(context)


def _crash_then_recover(h: Harness, crashes: int) -> str:
    h.service.submit_usecase(person("business_owner"), "case", "x" * 250)
    for _ in range(crashes + 1):
        with contextlib.suppress(RuntimeError):  # the crash propagates; the lease stays
            h.drain()
        h.clock.advance(timedelta(minutes=6))  # past the 5-minute lease
    h.drain()
    return h.runs("UC-0001")[0].run_id


def test_interrupted_step_is_retried_and_counted(orch_template: PlatformDatabase) -> None:
    with harness(orch_template, agent=CrashingAgent(crashes=1)) as h:
        run_id = _crash_then_recover(h, crashes=1)
        run = h.run(run_id)
        assert (run.state, run.auto_retries, run.rework_count) == ("awaiting_sign_off", 1, 0)


def test_interrupted_too_often_escalates(orch_template: PlatformDatabase) -> None:
    with harness(orch_template, agent=CrashingAgent(crashes=10)) as h:
        run_id = _crash_then_recover(h, crashes=4)
        run = h.run(run_id)
        assert (run.state, run.escalation_trigger) == ("escalated", "retry_limit")


def test_stale_result_is_discarded(orch_template: PlatformDatabase) -> None:
    holder: dict[str, Harness] = {}

    class SlowAgent(StubAgent):
        def build(self, context: BuildContext) -> AgentResult:
            h = holder["h"]
            # while the agent works, the run is escalated by its timer and terminated by a person
            h.orch.runs.apply(
                context.run_id,
                Signal(SignalKind.TIMER, ActorType.ORCHESTRATOR, "o", {"kind": "escalate_after"}),
            )
            h.service.decide(person("business_owner"), context.run_id, "terminate", comment="stop")
            return super().build(context)

    with harness(orch_template, agent=SlowAgent()) as h:
        holder["h"] = h
        h.service.submit_usecase(person("business_owner"), "case", "x" * 250)
        h.drain()
        run = h.runs("UC-0001")[0]
        assert run.final_status == "terminate"
        assert run.artifacts == {}
        stale = h.sql(
            "SELECT step, outcome FROM run.run_activity WHERE run_id = :r AND outcome = 'stale'",
            r=run.run_id,
        )
        assert [tuple(s) for s in stale] == [("build", "stale")]


@pytest.mark.parametrize("unused", [None])
def test_overdue_timers_fire_once_after_restart(
    h: Harness, unused: Callable[[], None] | None
) -> None:
    usecase, t1 = walk_to(h, "T1")
    h.clock.advance(timedelta(days=60))
    orch = restarted(h)
    orch.drain()
    orch.drain()
    assert (
        h.sql("SELECT count(*) FROM events.outbox_event WHERE event_type = 'T1.escalate'")[0][0]
        == 1
    )
