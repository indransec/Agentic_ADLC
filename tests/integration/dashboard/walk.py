"""013: a scripted walk with every kind of journey event, for the dashboard tests.

T2 asks a clarification (answered after 10 minutes); T4 is reworked with root cause
``implementation`` (routed back to T3); T5 passes with an exception and a waiver; T6's agent fails
its attempts until the run escalates and a person completes it; a drift event opens T9, which
re-enters the lifecycle at its class's terminal.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta

from adlc.orchestration.interfaces import AttemptFailed, Clarification
from adlc.orchestration.service import Actor
from adlc.orchestration.stubs import StubAgent
from adlc.policy.synthetic import load_synthetic_artifacts
from tests.support.orchestration import SYNTHETIC, Harness, harness, person
from tests.support.pg import PlatformDatabase

ASK = Clarification(("Which channels are in scope?",), looked_in=("intake",))
FAIL = AttemptFailed("the build did not fit")
WAIVER = {
    "risk_acceptance": "accepted",
    "expiry": "2099-12-31",
    "compensating_control": "manual check",
}


@dataclass
class Walked:
    h: Harness
    usecase: str


def _pass(h: Harness, terminal: str, usecase: str, fields: dict[str, str] | None = None) -> None:
    h.drain()
    h.pass_run(h.active(usecase, terminal).run_id, fields)


@contextmanager
def walked(db: PlatformDatabase) -> Iterator[Walked]:
    agent = StubAgent(
        {"T2": {1: ASK}, "T6": {1: FAIL, 2: FAIL, 3: FAIL, 4: FAIL}},
        base=load_synthetic_artifacts(SYNTHETIC),
    )
    with harness(db, agent=agent) as h:
        usecase = h.submit()
        _pass(h, "T0", usecase, {"risk_tier": "low"})
        _pass(h, "T1", usecase)
        h.drain()
        t2 = h.active(usecase, "T2")
        clarification = h.sql(
            "SELECT clarification_id, addressed_role FROM run.clarification_round"
        )[0]
        h.clock.advance(timedelta(minutes=10))
        h.service.answer_clarification(person(clarification[1]), clarification[0], ["web"])
        _pass(h, "T2", usecase)
        _pass(h, "T3", usecase)
        h.drain()
        t4 = h.active(usecase, "T4")
        h.service.decide(
            person("qa_eval_lead"),
            t4.run_id,
            "rework",
            comment="routing rules miss a team",
            root_cause="implementation",
            reason="the reviewer missed the routing gap",
            fields={"defect_log": "DEF-1 one team never routed"},
        )
        _pass(h, "T3", usecase)
        _pass(h, "T4", usecase)
        h.drain()
        t5 = h.active(usecase, "T5")
        h.service.decide(
            person("security_officer"), t5.run_id, "exception", reason="known gap", fields=WAIVER
        )
        h.drain()
        h.service.decide_waiver(person("risk_owner"), "WVR-0001", True, "accepted")
        h.drain()
        t6 = h.active(usecase, "T6")
        assert h.run(t6.run_id).state == "escalated"
        h.service.complete_escalation(person("release_manager"), t6.run_id, {**h.agent.base["T6"]})
        _pass(h, "T6", usecase)
        _pass(h, "T7", usecase)
        _pass(h, "T8", usecase)
        h.service.raise_operational_event(
            Actor.system("monitor"),
            usecase,
            "drift",
            {"monitor_id": "MON-04", "measured": {"x": 0.6}},
        )
        _pass(h, "T9", usecase)
        h.drain()
        assert t2 is not None
        yield Walked(h, usecase)
