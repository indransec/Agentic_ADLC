"""T033: parameters frozen per run, within guardrails (US3; FR-012 to FR-014)."""

from collections.abc import Mapping
from typing import Any

from adlc.orchestration.interfaces import EvalContext
from adlc.orchestration.stubs import StubAgent
from adlc.policy.factory import build_policy_engine
from adlc.spec_toolkit.registry import SqlSpecRegistry
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, harness, person
from tests.support.pg import PlatformDatabase


class Profile:
    def __init__(self, values: Mapping[str, Any]) -> None:
        self._values = values

    def values(self, usecase_id: str) -> Mapping[str, Any]:
        return self._values


def _set(h: Harness, run_id: str) -> tuple[Any, ...]:
    row = h.sql(
        "SELECT risk_tier, parameters, rejected FROM run.run_parameter_set WHERE run_id = :r",
        r=run_id,
    )
    assert len(row) == 1
    return tuple(row[0])


def test_frozen_at_run_open_and_reused(h: Harness) -> None:
    usecase, t1 = walk_to(h, "T1", tier="high")
    tier, parameters, rejected = _set(h, t1)
    assert tier == "high"
    assert parameters["autonomy_level_max"] == {"value": 4, "source": "guardrail"}
    assert rejected == []
    first = h.sql("SELECT resolved_at FROM run.run_parameter_set WHERE run_id = :r", r=t1)[0][0]
    engine = build_policy_engine(h.app, SqlSpecRegistry(h.app), h.clock)
    engine.evaluate("param.autonomy_level_max == 4", EvalContext("T1", "x", t1, usecase))
    assert (
        h.sql("SELECT resolved_at FROM run.run_parameter_set WHERE run_id = :r", r=t1)[0][0]
        == first
    )


def test_rework_run_resolves_its_own_set(h: Harness) -> None:
    usecase, t1 = walk_to(h, "T1")
    h.service.decide(
        person("product_owner"), t1, "rework", comment="c", root_cause="requirement", reason="r"
    )
    h.drain()
    run2 = h.active(usecase, "T1").run_id
    assert _set(h, run2)[1]["test_scenarios_min"]["value"] == 30
    assert (
        h.sql(
            "SELECT count(*) FROM run.run_parameter_set WHERE run_id LIKE :p", p=f"{usecase}/T1/%"
        )[0][0]
        == 2
    )


def test_profile_values_within_and_outside_guardrails(h: Harness) -> None:
    usecase, t1 = walk_to(h, "T1")
    engine = build_policy_engine(
        h.app,
        SqlSpecRegistry(h.app),
        h.clock,
        profile=Profile({"autonomy_level_max": 5, "test_scenarios_min": 40}),
    )
    # A fresh run of another terminal resolves with the profile.
    h.pass_run(t1)
    t2 = h.active(h.run(t1).usecase_id, "T2").run_id
    h.sql("SELECT 1")
    engine.evaluate("param.test_scenarios_min == 40", EvalContext("T2", "x", t2, usecase))
    tier, parameters, rejected = _set(h, t2)
    assert (
        parameters["test_scenarios_min"] == {"value": 30, "source": "guardrail"}
        or parameters["test_scenarios_min"]["source"] == "usecase"
    )


def test_unresolved_parameter(h: Harness) -> None:
    usecase, t1 = walk_to(h, "T1")
    engine = build_policy_engine(h.app, SqlSpecRegistry(h.app), h.clock)
    result = engine.evaluate("param.no_such_limit == 1", EvalContext("T1", "x", t1, usecase))
    assert (result.passed, result.reason) == (False, "evidence not available: param.no_such_limit")


def test_control_reads_the_tier_parameter(orch_template: PlatformDatabase) -> None:
    """US2/AC4: CTL-T1-05 autonomy level at most the maximum for the use case's tier."""
    level3 = {"autonomy_levels": {"autonomy_level": 3}}
    with harness(orch_template, agent=StubAgent({"T1": {n: level3 for n in range(1, 5)}})) as h:
        _, at_medium = walk_to(h, "T1", tier="medium")  # max 3
        assert h.run(at_medium).state == "awaiting_sign_off"
    with harness(orch_template, agent=StubAgent({"T1": {n: level3 for n in range(1, 5)}})) as h:
        _, at_low = walk_to(h, "T1", tier="low")  # max 2
        failed = [c for c in h.run(at_low).control_results if not c["passed"]]
        assert failed[0]["id"] == "CTL-T1-05"


def test_no_self_deadlock_when_a_decision_freezes_parameters(
    orch_template: PlatformDatabase,
) -> None:
    """A run opened escalated has no frozen parameters when it is decided; the plus-approver
    check then freezes them from a second connection while the run row is locked."""
    import threading

    from adlc.orchestration import store as run_store

    with harness(orch_template) as h:
        usecase, run_id = walk_to(h, "T1")
        for _ in range(4):  # the fourth rework opens run 5 escalated, without prerequisites
            h.service.decide(
                person("product_owner"),
                run_id,
                "rework",
                comment="c",
                root_cause="requirement",
                reason="r",
            )
            h.drain()
            run_id = h.active(usecase, "T1").run_id
        assert not h.sql("SELECT 1 FROM run.run_parameter_set WHERE run_id = :r", r=run_id)
        engine = build_policy_engine(h.app, SqlSpecRegistry(h.app), h.clock)
        done = threading.Event()

        def decide_under_lock() -> None:
            with h.app.begin() as conn:
                run_store.load_run(conn, run_id, lock=True)
                engine.evaluate(
                    "param.unit_coverage_min > 0", EvalContext("T1", "plus:x", run_id, usecase)
                )
            done.set()

        worker = threading.Thread(target=decide_under_lock, daemon=True)
        worker.start()
        worker.join(timeout=20)
        assert done.is_set(), "freezing parameters blocked on the locked run row"
        assert h.sql("SELECT 1 FROM run.run_parameter_set WHERE run_id = :r", r=run_id)
