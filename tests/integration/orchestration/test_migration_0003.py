"""T004: the 003 tables (data-model.md): constraints, append-only triggers and column guards."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from tests.support.db import column_names, table_names

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
    "run_transition",
    "run_activity",
    "sign_off",
    "clarification_round",
    "clarification_answer",
    "dead_letter_action",
)
EVENT_ID = "0193a6a0-0000-7000-8000-000000000001"


@pytest.fixture
def app(app_engine: Engine) -> Iterator[Connection]:
    with app_engine.connect() as conn:
        yield conn


def _seed(conn: Connection) -> None:
    conn.execute(
        text(
            "INSERT INTO usecase (usecase_id, name, intake_text, submitted_by) "
            "VALUES ('UC-0001', 'Claims triage', 'intake', 'alice')"
        )
    )
    conn.execute(
        text(
            "INSERT INTO terminal_run (run_id, usecase_id, terminal_id, run_number, "
            "spec_version, state, mode, trigger_event_type) "
            "VALUES ('UC-0001/T1/run-1', 'UC-0001', 'T1', 1, '1.0.0', 'opened', 'evolve', "
            "'T0.pass')"
        )
    )


def _refused(conn: Connection, sql: str) -> None:
    """Refused by a check, a unique index, a foreign key or a guard trigger."""
    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(text(sql))


def test_tables_exist(owner_engine: Engine) -> None:
    with owner_engine.connect() as conn:
        tables = table_names(conn)
        ledger_cols = set(column_names(conn, "ledger_record"))
    assert tables >= RUN_TABLES | EVENT_TABLES  # later features add their own
    assert {"run_id", "usecase_id", "content_json"} <= ledger_cols


def test_identifier_patterns(app: Connection) -> None:
    _refused(
        app,
        "INSERT INTO usecase (usecase_id, name, intake_text, submitted_by) "
        "VALUES ('UC-1', 'x', 'y', 'z')",
    )
    _seed(app)
    _refused(
        app,
        "INSERT INTO waiver (waiver_id, run_id, expiry, status, proposed_by) "
        "VALUES ('W-1', 'UC-0001/T1/run-1', '2099-01-01', 'proposed', 'bob')",
    )
    _refused(
        app,
        "INSERT INTO terminal_run (run_id, usecase_id, terminal_id, run_number, "
        "spec_version, state, mode, trigger_event_type) VALUES "
        "('UC-0001/T1/run-9', 'UC-0001', 'T1', 9, '1.0.0', 'dancing', 'evolve', 'x')",
    )


def test_one_active_run_per_terminal(app: Connection) -> None:
    _seed(app)
    second = (
        "INSERT INTO terminal_run (run_id, usecase_id, terminal_id, run_number, "
        "spec_version, state, mode, trigger_event_type) VALUES "
        "('UC-0001/T1/run-2', 'UC-0001', 'T1', 2, '1.0.0', 'opened', 'evolve', 'x')"
    )
    with pytest.raises(IntegrityError), app.begin_nested():
        app.execute(text(second))
    app.execute(
        text(
            "UPDATE terminal_run SET state = 'closed', final_status = 'rework' "
            "WHERE run_id = 'UC-0001/T1/run-1'"
        )
    )
    app.execute(text(second))


def test_closed_run_is_frozen(app: Connection) -> None:
    _seed(app)
    app.execute(text("UPDATE terminal_run SET state = 'closed', final_status = 'pass'"))
    _refused(app, "UPDATE terminal_run SET artifacts = '{}'")


SEED_ROWS = {
    "run_transition": "INSERT INTO run_transition (run_id, to_state, signal_kind, "
    "actor_type, actor_id) VALUES ('UC-0001/T1/run-1', 'opened', 'open', 'orchestrator', 'o')",
    "run_activity": "INSERT INTO run_activity (run_id, step, actor_type, actor_id, "
    "started_at, ended_at, outcome) VALUES ('UC-0001/T1/run-1', 'build', 'agent', 'a', now(), "
    "now(), 'ok')",
    "sign_off": "INSERT INTO sign_off (run_id, role, person, decision) "
    "VALUES ('UC-0001/T1/run-1', 'product_owner', 'p', 'pass')",
    "clarification_round": "INSERT INTO clarification_round (clarification_id, run_id, "
    "asked_by, addressed_role, questions) VALUES ('UC-0001/T1/run-1/clar-1', "
    "'UC-0001/T1/run-1', 'agent', 'business_owner', '[]')",
    "clarification_answer": "INSERT INTO clarification_answer (clarification_id, "
    "answered_by, answers) VALUES ('UC-0001/T1/run-1/clar-1', 'b', '[]')",
    "dead_letter_action": "INSERT INTO dead_letter_action (event_id, action, actor) "
    "SELECT event_id, 'requeue', 'coe' FROM outbox_event",
}


def test_append_only_tables(app_engine: Engine) -> None:
    with app_engine.begin() as conn:
        _seed(conn)
        conn.execute(
            text(
                "INSERT INTO outbox_event (event_id, event_type, usecase_id, "
                "correlation_id, payload) VALUES (:e, 'T1.pass', 'UC-0001', "
                "'UC-0001/lifecycle', '{}')"
            ),
            {"e": EVENT_ID},
        )
        for table in APPEND_ONLY:
            conn.execute(text(SEED_ROWS[table]))
    with app_engine.connect() as conn:
        for table in APPEND_ONLY:
            column = column_names(conn, table)[-1]
            for sql in (f"UPDATE {table} SET {column} = {column}", f"DELETE FROM {table}"):
                with pytest.raises(IntegrityError) as info, conn.begin_nested():
                    conn.execute(text(sql))
                assert "append-only" in str(info.value.orig), (table, sql)


def test_column_guards(app: Connection) -> None:
    _seed(app)
    app.execute(text("UPDATE usecase SET risk_tier = 'high', status = 'closed'"))
    _refused(app, "UPDATE usecase SET name = 'renamed'")
    app.execute(
        text(
            "INSERT INTO outbox_event (event_id, event_type, usecase_id, correlation_id, "
            "payload) VALUES (:e, 'T1.pass', 'UC-0001', 'UC-0001/lifecycle', '{}')"
        ),
        {"e": EVENT_ID},
    )
    app.execute(text("UPDATE outbox_event SET attempts = 1, last_error = 'boom'"))
    _refused(app, "UPDATE outbox_event SET payload = '{\"x\": 1}'")
    app.execute(
        text(
            "INSERT INTO waiver (waiver_id, run_id, expiry, status, proposed_by) "
            "VALUES ('WVR-0001', 'UC-0001/T1/run-1', '2099-01-01', 'proposed', 'bob')"
        )
    )
    _refused(app, "UPDATE waiver SET expiry = '2100-01-01'")
    app.execute(
        text("UPDATE waiver SET status = 'approved', decided_by = 'carol', decided_at = now()")
    )
    _refused(app, "UPDATE waiver SET status = 'rejected'")


def test_ledger_extension_stays_append_only(app: Connection) -> None:
    app.execute(
        text(
            "INSERT INTO ledger_record (ledger_key, content_hash, run_id, usecase_id, "
            "content_json) VALUES ('UC-0001/T1/run-1', :h, 'UC-0001/T1/run-1', 'UC-0001', '{}')"
        ),
        {"h": "sha256:" + "a" * 64},
    )
    _refused(
        app,
        "INSERT INTO ledger_record (ledger_key, content_hash, run_id) VALUES "
        f"('other', 'sha256:{'b' * 64}', 'UC-0001/T1/run-1')",
    )
    _refused(app, "UPDATE ledger_record SET content_json = '{}'")
