"""T022: the versioned use-case profile (US3; FR-013 to FR-015; SC-005)."""

import pytest

from adlc.ledger.profile import SqlProfileSource
from adlc.orchestration.interfaces import EvalContext
from adlc.orchestration.service import Actor, InvalidDecision
from adlc.policy.factory import build_policy_engine
from adlc.spec_toolkit.registry import SqlSpecRegistry
from tests.support.db import PlatformDatabase
from tests.support.lifecycle import walk_to
from tests.support.orchestration import SYNTHETIC, Harness, harness, person


def _versions(h: Harness, usecase: str) -> list[tuple[int, dict, str]]:  # type: ignore[type-arg]
    rows = h.sql(
        "SELECT version, profile_values, source_run_id FROM profile_version WHERE usecase_id = :u ORDER BY version",
        u=usecase,
    )
    return [(int(r[0]), dict(r[1]), str(r[2])) for r in rows]


def test_versions_grow_with_passes(h: Harness) -> None:
    usecase, t3 = walk_to(h, "T3")
    versions = _versions(h, usecase)
    assert [v[0] for v in versions] == [1, 2, 3]
    assert versions[0][1]["risk_tier"] == "medium"  # T0 emits risk_tier
    assert versions[1][1]["kpis"]["artifact"] == "kpis"  # T1 emits artifacts by reference
    assert "token_budget" in versions[2][1] and "kpis" in versions[2][1]  # merged
    assert h.run(t3).profile_version == 3
    assert [v[2] for v in versions] == [
        f"{usecase}/T0/run-1",
        f"{usecase}/T1/run-1",
        f"{usecase}/T2/run-1",
    ]


def test_rework_and_terminate_add_no_version(h: Harness) -> None:
    usecase, t1 = walk_to(h, "T1")
    h.service.decide(
        person("product_owner"), t1, "rework", comment="c", root_cause="requirement", reason="r"
    )
    h.drain()
    assert [v[0] for v in _versions(h, usecase)] == [1]
    h.service.decide(
        person("business_owner"), h.active(usecase, "T1").run_id, "terminate", comment="stop"
    )
    assert [v[0] for v in _versions(h, usecase)] == [1]


def test_repass_supersedes_and_old_versions_stay(h: Harness) -> None:
    usecase, t2 = walk_to(h, "T2")
    first_kpis = _versions(h, usecase)[1][1]["kpis"]
    h.agent.script = {"T1": {2: {"kpis": {"target": 7}}}}  # run 2 builds different KPIs
    h.service.decide(
        person("security_officer"), t2, "rework", comment="c", root_cause="requirement", reason="r"
    )
    h.drain()
    t1_run2 = h.active(usecase, "T1").run_id
    h.pass_run(t1_run2)
    versions = _versions(h, usecase)
    assert len(versions) == 3 and versions[1][1]["kpis"] == first_kpis
    assert versions[2][1]["kpis"]["content_hash"] != first_kpis["content_hash"]


def test_open_runs_keep_their_version(h: Harness) -> None:
    usecase, t1 = walk_to(h, "T1")
    source = SqlProfileSource(h.app)
    assert h.run(t1).profile_version == 1
    h.pass_run(t1)
    assert dict(source.values(usecase, t1)) == _versions(h, usecase)[0][1]  # still version 1
    assert dict(source.values(usecase)) == _versions(h, usecase)[1][1]  # current is version 2


def test_profile_value_drives_parameters(orch_template: PlatformDatabase) -> None:
    """SC-005: a value within the guardrail is used; a looser one is rejected and recorded."""
    with harness(orch_template) as h:
        usecase, t2 = walk_to(h, "T2")
        with h.app.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO profile_version (usecase_id, version, profile_values, source_run_id) "
                f"VALUES ('{usecase}', 4, '{{\"autonomy_level_max\": {{\"value\": 2}}, \"test_scenarios_min\": 10}}', '{t2}')"
            )
        h.pass_run(t2)
        t3 = h.active(usecase, "T3").run_id
        row = h.sql("SELECT parameters, rejected FROM run_parameter_set WHERE run_id = :r", r=t3)[0]
        assert row[0]["autonomy_level_max"] == {"value": 2, "source": "usecase"}
        assert row[0]["test_scenarios_min"]["source"] == "guardrail"
        assert row[1][0]["name"] == "test_scenarios_min"


def test_profile_evidence_is_real(h: Harness) -> None:
    usecase, t2 = walk_to(h, "T2")
    engine = build_policy_engine(h.app, SqlSpecRegistry(h.app), h.clock, synthetic_dir=SYNTHETIC)
    result = engine.evaluate(
        "profile.risk_tier == 'medium'", EvalContext("T2", "probe", t2, usecase)
    )
    assert result.passed and not result.synthetic


T0_EXCEPTION = {
    "waiver_owner": "business_owner-person",
    "expiry": "2099-12-31",
    "compensating_control": "manual review",
}


def test_exception_emits_like_a_pass(h: Harness) -> None:
    """An exception waives controls, not the hand-off: T0's tier and profile still go forward."""
    usecase = h.submit()
    h.drain()
    t0 = h.active(usecase, "T0").run_id
    owner = person("business_owner")
    with pytest.raises(InvalidDecision, match="risk_tier"):
        h.service.decide(owner, t0, "exception", reason="r", fields=T0_EXCEPTION)
    h.service.decide(
        owner, t0, "exception", reason="r", fields={**T0_EXCEPTION, "risk_tier": "high"}
    )
    waiver = h.run(t0).pending_waiver_id
    assert waiver is not None
    h.service.decide_waiver(Actor("second-owner", frozenset({"business_owner"})), waiver, True)
    h.drain()
    assert h.run(t0).final_status == "exception"
    assert h.sql("SELECT risk_tier FROM usecase WHERE usecase_id = :u", u=usecase)[0][0] == "high"
    versions = _versions(h, usecase)
    assert versions[-1][1]["risk_tier"] == "high"
    assert versions[-1][2] == f"{usecase}/T0/run-1"
    record = h.sql("SELECT content_json FROM ledger_record WHERE run_id = :r", r=t0)[0][0]
    assert record["emitted"]["risk_tier"] == "high"
