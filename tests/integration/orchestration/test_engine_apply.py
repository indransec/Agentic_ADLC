"""T021: one transaction per signal; atomic close (FR-026, SC-007, constitution V)."""

import threading

import pytest

from adlc.orchestration import store
from adlc.orchestration.engine import StaleRun
from adlc.orchestration.service import Actor
from adlc.orchestration.states import ActorType, InvalidTransition, Signal, SignalKind
from adlc.orchestration.stubs import StubAgent
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, harness, person
from tests.support.pg import PlatformDatabase


def _at_sign_off(h: Harness, terminal: str = "T0") -> tuple[str, str]:
    usecase = h.submit()
    for t in ("T0", "T1", "T2", "T3", "T4")[: ("T0", "T1", "T2", "T3", "T4").index(terminal)]:
        h.pass_run(h.active(usecase, t).run_id, {"risk_tier": "medium"})
    return usecase, h.active(usecase, terminal).run_id


def test_apply_writes_transition_activity_and_version(h: Harness) -> None:
    usecase, run_id = _at_sign_off(h)
    run = h.run(run_id)
    transitions = h.sql(
        "SELECT from_state, to_state FROM run.run_transition WHERE run_id = :r ORDER BY run_transition_id",
        r=run_id,
    )
    assert [tuple(t) for t in transitions] == [
        (None, "opened"),
        ("opened", "building"),
        ("building", "checking"),
        ("checking", "reviewing"),
        ("reviewing", "awaiting_sign_off"),
    ]
    steps = [
        r[0]
        for r in h.sql(
            "SELECT step FROM run.run_activity WHERE run_id = :r ORDER BY run_activity_id", r=run_id
        )
    ]
    assert steps == ["route", "prerequisites", "build", "controls", "review"]
    assert run.version == 4


def test_stale_version_writes_nothing(h: Harness) -> None:
    _, run_id = _at_sign_off(h)
    before = h.run(run_id)
    with pytest.raises(StaleRun):
        h.service.decide(
            person("business_owner"),
            run_id,
            "pass",
            fields={"risk_tier": "low"},
            expected_version=before.version - 1,
        )
    assert h.run(run_id) == before
    assert h.sql("SELECT count(*) FROM run.sign_off")[0][0] == 0


def test_invalid_transition_writes_nothing(h: Harness) -> None:
    _, run_id = _at_sign_off(h)
    before = h.run(run_id)
    with pytest.raises(InvalidTransition):
        h.orch.runs.apply(
            run_id, Signal(SignalKind.AGENT_RESULT, ActorType.AGENT, "a", {"result": "artifacts"})
        )
    assert h.run(run_id) == before


def test_close_writes_everything_together(h: Harness) -> None:
    usecase, run_id = _at_sign_off(h)
    h.service.decide(person("business_owner"), run_id, "pass", fields={"risk_tier": "high"})
    run = h.run(run_id)
    assert (run.state, run.final_status) == ("closed", "pass")
    assert h.sql("SELECT count(*) FROM ledger.ledger_record WHERE run_id = :r", r=run_id)[0][0] == 1
    assert (
        h.sql(
            "SELECT count(*) FROM events.outbox_event WHERE causation_run_id = :r AND event_type = 'T0.pass'",
            r=run_id,
        )[0][0]
        == 1
    )
    assert h.sql("SELECT count(*) FROM run.sign_off WHERE run_id = :r", r=run_id)[0][0] == 1
    open_timers = h.sql(
        "SELECT count(*) FROM run.timer WHERE run_id = :r AND fired_at IS NULL AND cancelled_at IS NULL",
        r=run_id,
    )
    assert open_timers[0][0] == 0
    assert h.service.get_usecase(usecase).risk_tier == "high"


def test_failure_mid_close_leaves_nothing(h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    _, run_id = _at_sign_off(h)
    before = h.run(run_id)

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("crash after the ledger insert")

    monkeypatch.setattr(store, "insert_event", boom)
    with pytest.raises(RuntimeError):
        h.service.decide(person("business_owner"), run_id, "pass", fields={"risk_tier": "low"})
    assert h.run(run_id) == before
    assert h.sql("SELECT count(*) FROM ledger.ledger_record")[0][0] == 0
    assert h.sql("SELECT count(*) FROM run.sign_off")[0][0] == 0


def test_concurrent_closes_keep_one_chain(orch_template: PlatformDatabase) -> None:
    """Two runs of one use case closed at the same moment: one unbroken chain (C3)."""
    agent = StubAgent({"T9": {1: {"change_impact_assessment": {"reentry_terminal": "T2"}}}})
    with harness(orch_template, agent=agent) as h:
        usecase, t5 = walk_to(h, "T5")  # T9 needs T3 and T4 evidence before it can build
        h.service.raise_operational_event(Actor.system("monitor"), usecase, "drift", {})
        h.drain()  # T9 opens on the drift event while T5 is still open
        runs = [t5, h.active(usecase, "T9").run_id]
        barrier = threading.Barrier(2)
        errors: list[BaseException] = []

        def close(run_id: str) -> None:
            try:
                barrier.wait()
                h.pass_run(run_id)
            except BaseException as exc:  # noqa: BLE001 - reported below
                errors.append(exc)

        threads = [threading.Thread(target=close, args=(r,)) for r in runs]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        chain = h.sql(
            "SELECT content_hash, previous_record_hash FROM ledger.ledger_record "
            "WHERE usecase_id = :u ORDER BY ledger_record_id",
            u=usecase,
        )
        assert len(chain) == 7  # T0-T4, then T5 and T9 closed concurrently
        assert chain[0][1] is None
        assert [c[1] for c in chain[1:]] == [c[0] for c in chain[:-1]]
