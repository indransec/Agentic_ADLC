"""T036: every decision recorded, append-only, ordered, labelled (US4; FR-019 to FR-021; SC-004, SC-009)."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from adlc.orchestration.interfaces import EvalContext
from adlc.policy.factory import build_policy_engine
from adlc.spec_toolkit.registry import SqlSpecRegistry
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness


def test_one_record_per_check_with_inputs(h: Harness) -> None:
    usecase, t1 = walk_to(h, "T1")
    rows = h.sql(
        "SELECT kind, run_id, usecase_id, terminal_id, check_id, rule, passed, reason, inputs, "
        "synthetic, fail_safe, duration_ms FROM run.policy_decision WHERE run_id = :r "
        "ORDER BY decided_at, policy_decision_id",
        r=t1,
    )
    checks = [r[4] for r in rows]
    assert checks[:3] == ["PRE-T1-01", "PRE-T1-02", "PRE-T1-03"]
    assert {"CTL-T1-01", "CTL-T1-06"} <= set(checks)
    numeric = [r for r in rows if r[4] == "CTL-T1-02"][0]
    assert (numeric[0], numeric[3], numeric[6], numeric[7]) == ("evaluate", "T1", True, "passed")
    table = numeric[8]["T1.kpis"]["value"]
    assert set(table) == {"ref", "rows", "content_hash"} and table["rows"] == 2


def test_records_are_append_only(h: Harness) -> None:
    walk_to(h, "T1")
    for engine in (h.app, h.owner):
        with engine.connect() as conn:
            for sql in (
                "UPDATE run.policy_decision SET passed = NOT passed",
                "DELETE FROM run.policy_decision",
            ):
                with pytest.raises(DBAPIError), conn.begin_nested():
                    conn.execute(text(sql))


def test_kept_when_the_caller_rolls_back(h: Harness) -> None:
    usecase, t1 = walk_to(h, "T1")
    engine = build_policy_engine(h.app, SqlSpecRegistry(h.app), h.clock)
    before = h.sql("SELECT count(*) FROM run.policy_decision")[0][0]
    with h.app.connect() as conn:
        tx = conn.begin()
        engine.evaluate("1 == 1", EvalContext("T1", "probe", t1, usecase))
        tx.rollback()
    assert h.sql("SELECT count(*) FROM run.policy_decision")[0][0] == before + 1


def test_synthetic_label_only_when_synthetic_was_read(h: Harness) -> None:
    usecase = h.submit()
    t0 = h.active(usecase, "T0").run_id
    labels = dict(
        h.sql("SELECT check_id, synthetic FROM run.policy_decision WHERE run_id = :r", r=t0)
    )
    assert labels["PRE-T0-02"] is True  # in_directory read the synthetic directory
    assert labels["PRE-T0-01"] is False  # size(intake.free_text) read real intake only
    assert labels["CTL-T0-02"] is False
