"""T002: migration 0004 (data-model.md): decision log and frozen parameter sets, append-only."""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from tests.support.pg import PlatformDatabase, alembic

DECISION_COLUMNS = {
    "policy_decision_id",
    "kind",
    "run_id",
    "usecase_id",
    "terminal_id",
    "check_id",
    "rule",
    "actor",
    "passed",
    "value",
    "reason",
    "inputs",
    "synthetic",
    "fail_safe",
    "duration_ms",
    "decided_at",
    "attempt",  # added by migration 0005 (the build attempt of a control decision)
}
PARAMETER_COLUMNS = {
    "run_id",
    "risk_tier",
    "guardrail_version",
    "parameters",
    "rejected",
    "resolved_at",
}


def _columns(engine: Engine, table: str) -> set[str]:
    with engine.connect() as conn:
        return set(
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'run' AND table_name = :t"
                ),
                {"t": table},
            ).scalars()
        )


def test_tables_and_index(owner_engine: Engine) -> None:
    assert _columns(owner_engine, "policy_decision") == DECISION_COLUMNS
    assert _columns(owner_engine, "run_parameter_set") == PARAMETER_COLUMNS
    with owner_engine.connect() as conn:
        index = conn.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'policy_decision_by_run'")
        ).scalar_one()
    assert "(run_id, decided_at, policy_decision_id)" in index


def test_grants(app_engine: Engine) -> None:
    with app_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
                "WHERE grantee = current_user AND table_name IN ('policy_decision', 'run_parameter_set')"
            )
        ).all()
    grants: dict[str, set[str]] = {}
    for table, privilege in rows:
        grants.setdefault(table, set()).add(privilege)
    assert grants == {
        "policy_decision": {"SELECT", "INSERT"},
        "run_parameter_set": {"SELECT", "INSERT"},
    }


def _seed(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO run.usecase (usecase_id, name, intake_text, submitted_by) "
                "VALUES ('UC-0001', 'n', 'i', 'o')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO run.terminal_run (run_id, usecase_id, terminal_id, run_number, "
                "spec_version, state, mode, trigger_event_type) VALUES ('UC-0001/T1/run-1', "
                "'UC-0001', 'T1', 1, '1.0.0', 'opened', 'evolve', 'T0.pass')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO run.policy_decision (kind, run_id, check_id, rule, passed, reason, "
                "inputs, synthetic, fail_safe, duration_ms) VALUES ('evaluate', "
                "'UC-0001/T1/run-1', 'CTL-T1-01', 'true', true, 'passed', '{}', false, false, 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO run.run_parameter_set (run_id, risk_tier, guardrail_version, "
                "parameters, rejected) VALUES ('UC-0001/T1/run-1', 'medium', '1.0.0', '{}', '[]')"
            )
        )


def test_constraints(app_engine: Engine) -> None:
    _seed(app_engine)
    with app_engine.connect() as conn:
        for sql in (
            "INSERT INTO run.policy_decision (kind, check_id, rule, passed, reason, inputs, "
            "synthetic, fail_safe, duration_ms) VALUES ('guess', 'x', 'x', true, 'r', '{}', false, false, 1)",
            "INSERT INTO run.policy_decision (kind, check_id, rule, passed, reason, inputs, "
            "synthetic, fail_safe, duration_ms) VALUES ('evaluate', 'x', 'x', true, repeat('r', 2001), '{}', false, false, 1)",
        ):
            with pytest.raises(DBAPIError), conn.begin_nested():
                conn.execute(text(sql))


@pytest.mark.parametrize("table", ["run.policy_decision", "run.run_parameter_set"])
def test_append_only(app_engine: Engine, owner_engine: Engine, table: str) -> None:
    _seed(app_engine)
    for engine in (app_engine, owner_engine):
        with engine.connect() as conn:
            for sql in (
                f"UPDATE {table} SET run_id = run_id",
                f"DELETE FROM {table}",
                f"TRUNCATE {table}",
            ):
                with pytest.raises(DBAPIError), conn.begin_nested():
                    conn.execute(text(sql))


def test_downgrade_and_upgrade(migrated_db: PlatformDatabase) -> None:
    alembic(migrated_db, "downgrade", "0003")
    alembic(migrated_db, "upgrade", "head")
