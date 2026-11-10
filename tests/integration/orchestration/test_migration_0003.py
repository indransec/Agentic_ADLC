"""T004: migration 0003 (data-model.md): tables, constraints, append-only triggers, app grants."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from tests.support.pg import PlatformDatabase, alembic

RUN_TABLES = {
    "usecase",
    "terminal_run",
    "run_transition",
    "run_activity",
    "sign_off",
    "waiver",
    "clarification_round",
    "clarification_answer",
    "timer",
}
EVENT_TABLES = {"outbox_event", "processed_event", "dead_letter_action", "orchestrator_heartbeat"}
APPEND_ONLY = (
    "run.run_transition",
    "run.run_activity",
    "run.sign_off",
    "run.clarification_round",
    "run.clarification_answer",
    "events.dead_letter_action",
)
EXPECTED_GRANTS = {
    "run.usecase": {"SELECT", "INSERT", "UPDATE"},
    "run.terminal_run": {"SELECT", "INSERT", "UPDATE"},
    "run.run_transition": {"SELECT", "INSERT"},
    "run.run_activity": {"SELECT", "INSERT"},
    "run.sign_off": {"SELECT", "INSERT"},
    "run.waiver": {"SELECT", "INSERT", "UPDATE"},
    "run.clarification_round": {"SELECT", "INSERT"},
    "run.clarification_answer": {"SELECT", "INSERT"},
    "run.timer": {"SELECT", "INSERT", "UPDATE"},
    "events.outbox_event": {"SELECT", "INSERT", "UPDATE"},
    "events.processed_event": {"SELECT", "INSERT"},
    "events.dead_letter_action": {"SELECT", "INSERT"},
    "events.orchestrator_heartbeat": {"SELECT", "INSERT", "UPDATE"},
}


@pytest.fixture
def app(app_engine: Engine) -> Iterator[Connection]:
    with app_engine.connect() as conn:
        yield conn


def _seed(conn: Connection) -> None:
    conn.execute(
        text(
            "INSERT INTO run.usecase (usecase_id, name, intake_text, business_owner) "
            "VALUES ('UC-0001', 'Claims triage', 'intake', 'alice')"
        )
    )
    conn.execute(
        text(
            "INSERT INTO run.terminal_run (run_id, usecase_id, terminal_id, run_number, "
            "spec_version, state, mode, trigger_event_type) "
            "VALUES ('UC-0001/T1/run-1', 'UC-0001', 'T1', 1, '1.0.0', 'opened', 'evolve', "
            "'T0.pass')"
        )
    )


def _refused(conn: Connection, sql: str) -> None:
    with pytest.raises(DBAPIError) as info, conn.begin_nested():
        conn.execute(text(sql))
    assert getattr(info.value.orig, "sqlstate", None) in ("42501", "23514", "23505", "23503")


def test_tables_exist(owner_engine: Engine) -> None:
    with owner_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_schema IN ('run', 'events')"
            )
        ).all()
        ledger_cols = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'ledger' AND table_name = 'ledger_record'"
                )
            )
        }
    assert {t for s, t in rows if s == "run"} == RUN_TABLES
    assert {t for s, t in rows if s == "events"} == EVENT_TABLES
    assert {"run_id", "usecase_id", "content_json"} <= ledger_cols


def test_app_grants_are_exact(app: Connection) -> None:
    grants: dict[str, set[str]] = {}
    for table, privilege in app.execute(
        text(
            "SELECT table_schema || '.' || table_name, privilege_type "
            "FROM information_schema.role_table_grants WHERE grantee = current_user "
            "AND table_schema IN ('run', 'events')"
        )
    ):
        grants.setdefault(table, set()).add(privilege)
    assert grants == EXPECTED_GRANTS
    pin = app.execute(
        text(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = current_user AND table_name = 'usecase_spec_pin'"
        )
    ).scalars()
    assert set(pin) == {"SELECT", "INSERT"}


def test_identifier_patterns(app: Connection) -> None:
    _refused(
        app,
        "INSERT INTO run.usecase (usecase_id, name, intake_text, business_owner) "
        "VALUES ('UC-1', 'x', 'y', 'z')",
    )
    _seed(app)
    _refused(
        app,
        "INSERT INTO run.waiver (waiver_id, run_id, expiry, status, proposed_by) "
        "VALUES ('W-1', 'UC-0001/T1/run-1', '2099-01-01', 'proposed', 'bob')",
    )
    _refused(
        app,
        "INSERT INTO run.terminal_run (run_id, usecase_id, terminal_id, run_number, "
        "spec_version, state, mode, trigger_event_type) VALUES "
        "('UC-0001/T1/run-9', 'UC-0001', 'T1', 9, '1.0.0', 'dancing', 'evolve', 'x')",
    )


def test_one_active_run_per_terminal(app: Connection) -> None:
    _seed(app)
    second = (
        "INSERT INTO run.terminal_run (run_id, usecase_id, terminal_id, run_number, "
        "spec_version, state, mode, trigger_event_type) VALUES "
        "('UC-0001/T1/run-2', 'UC-0001', 'T1', 2, '1.0.0', 'opened', 'evolve', 'x')"
    )
    with pytest.raises(IntegrityError), app.begin_nested():
        app.execute(text(second))
    app.execute(
        text(
            "UPDATE run.terminal_run SET state = 'closed', final_status = 'rework' "
            "WHERE run_id = 'UC-0001/T1/run-1'"
        )
    )
    app.execute(text(second))


def test_closed_run_is_frozen(app: Connection) -> None:
    _seed(app)
    app.execute(text("UPDATE run.terminal_run SET state = 'closed', final_status = 'pass'"))
    _refused(app, "UPDATE run.terminal_run SET artifacts = '{}'::jsonb")


SEED_ROWS = {
    "run.run_transition": "INSERT INTO run.run_transition (run_id, to_state, signal_kind, "
    "actor_type, actor_id) VALUES ('UC-0001/T1/run-1', 'opened', 'open', 'orchestrator', 'o')",
    "run.run_activity": "INSERT INTO run.run_activity (run_id, step, actor_type, actor_id, "
    "started_at, ended_at, outcome) VALUES ('UC-0001/T1/run-1', 'build', 'agent', 'a', now(), "
    "now(), 'ok')",
    "run.sign_off": "INSERT INTO run.sign_off (run_id, role, person, decision) "
    "VALUES ('UC-0001/T1/run-1', 'product_owner', 'p', 'pass')",
    "run.clarification_round": "INSERT INTO run.clarification_round (clarification_id, run_id, "
    "asked_by, addressed_role, questions) VALUES ('UC-0001/T1/run-1/clar-1', "
    "'UC-0001/T1/run-1', 'agent', 'business_owner', '[]')",
    "run.clarification_answer": "INSERT INTO run.clarification_answer (clarification_id, "
    "answered_by, answers) VALUES ('UC-0001/T1/run-1/clar-1', 'b', '[]')",
    "events.dead_letter_action": "INSERT INTO events.dead_letter_action (event_id, action, actor) "
    "SELECT event_id, 'requeue', 'coe' FROM events.outbox_event",
}


def test_append_only_tables(app_engine: Engine, owner_engine: Engine) -> None:
    with app_engine.begin() as conn:
        _seed(conn)
        conn.execute(
            text(
                "INSERT INTO events.outbox_event (event_id, event_type, usecase_id, "
                "correlation_id, payload) VALUES (gen_random_uuid(), 'T1.pass', 'UC-0001', "
                "'UC-0001/lifecycle', '{}')"
            )
        )
        for table in APPEND_ONLY:
            conn.execute(text(SEED_ROWS[table]))
    for engine in (app_engine, owner_engine):
        with engine.connect() as conn:
            for table in APPEND_ONLY:
                column = _any_column(conn, table)
                for sql in (f"UPDATE {table} SET {column} = {column}", f"DELETE FROM {table}"):
                    with pytest.raises(DBAPIError) as info, conn.begin_nested():
                        conn.execute(text(sql))
                    assert info.value.orig.sqlstate == "42501", (table, sql)  # type: ignore[union-attr]
                with pytest.raises(DBAPIError), conn.begin_nested():
                    conn.execute(text(f"TRUNCATE {table} CASCADE"))


def _any_column(conn: Connection, table: str) -> str:
    schema, name = table.split(".")
    return str(
        conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = :s AND table_name = :t ORDER BY ordinal_position DESC LIMIT 1"
            ),
            {"s": schema, "t": name},
        ).scalar_one()
    )


def test_column_guards(app: Connection) -> None:
    _seed(app)
    app.execute(text("UPDATE run.usecase SET risk_tier = 'high', status = 'closed'"))
    _refused(app, "UPDATE run.usecase SET name = 'renamed'")
    app.execute(
        text(
            "INSERT INTO events.outbox_event (event_id, event_type, usecase_id, correlation_id, "
            "payload) VALUES (gen_random_uuid(), 'T1.pass', 'UC-0001', 'UC-0001/lifecycle', '{}')"
        )
    )
    app.execute(text("UPDATE events.outbox_event SET attempts = 1, last_error = 'boom'"))
    _refused(app, "UPDATE events.outbox_event SET payload = '{\"x\": 1}'::jsonb")
    app.execute(
        text(
            "INSERT INTO run.waiver (waiver_id, run_id, expiry, status, proposed_by) "
            "VALUES ('WVR-0001', 'UC-0001/T1/run-1', '2099-01-01', 'proposed', 'bob')"
        )
    )
    _refused(app, "UPDATE run.waiver SET expiry = '2100-01-01'")
    app.execute(
        text("UPDATE run.waiver SET status = 'approved', decided_by = 'carol', decided_at = now()")
    )
    _refused(app, "UPDATE run.waiver SET status = 'rejected'")


def test_ledger_extension_stays_append_only(app: Connection) -> None:
    app.execute(
        text(
            "INSERT INTO ledger.ledger_record (ledger_key, content_hash, run_id, usecase_id, "
            "content_json) VALUES ('UC-0001/T1/run-1', 'sha256:' || repeat('a', 64), "
            "'UC-0001/T1/run-1', 'UC-0001', '{}')"
        )
    )
    _refused(
        app,
        "INSERT INTO ledger.ledger_record (ledger_key, content_hash, run_id) VALUES "
        "('other', 'sha256:' || repeat('b', 64), 'UC-0001/T1/run-1')",
    )
    _refused(app, "UPDATE ledger.ledger_record SET content_json = '{}'")


def test_downgrade_and_upgrade_again(migrated_db: PlatformDatabase) -> None:
    alembic(migrated_db, "downgrade", "0002")
    alembic(migrated_db, "upgrade", "head")
