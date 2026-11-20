"""T003: the 005 tables (data-model.md): ledger content, versions, profile, verification, views."""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from tests.support.db import column_info, table_names

HASH = "sha256:" + "a" * 64
TABLES = (
    "content_blob",
    "file_object",
    "profile_version",
    "verification_run",
    "artifact_version",
    "artifact_attachment",
    "checklist_result",
)
VIEWS = ("v_run_step", "v_usecase_terminal_summary")


def _seed(engine: Engine) -> None:
    with engine.begin() as conn:
        for sql in (
            "INSERT INTO usecase (usecase_id, name, intake_text, submitted_by) VALUES ('UC-0001', 'n', 'i', 'o')",
            "INSERT INTO terminal_run (run_id, usecase_id, terminal_id, run_number, spec_version, state, mode, trigger_event_type) VALUES ('UC-0001/T1/run-1', 'UC-0001', 'T1', 1, '1.0.0', 'opened', 'evolve', 'T0.pass')",
            f"INSERT INTO content_blob (content_hash, body, size) VALUES ('{HASH}', '[]', 2)",
            f"INSERT INTO file_object (content_hash, size, media_type) VALUES ('{HASH}', 3, 'text/plain')",
            "INSERT INTO profile_version (usecase_id, version, profile_values, source_run_id) VALUES ('UC-0001', 1, '{}', 'UC-0001/T1/run-1')",
            "INSERT INTO verification_run (actor, scope, started_at, finished_at, records_checked, breaks, verified) VALUES ('a', 'all', now(), now(), 0, '[]', true)",
            f"INSERT INTO artifact_version (run_id, artifact_id, version, content_hash, producer_type, producer_id, schema_valid) VALUES ('UC-0001/T1/run-1', 'kpis', 1, '{HASH}', 'agent', 'agent:x', true)",
            f"INSERT INTO artifact_attachment (run_id, artifact_id, version, content_hash, file_name, media_type, size) VALUES ('UC-0001/T1/run-1', 'kpis', 1, '{HASH}', 'a.txt', 'text/plain', 3)",
            "INSERT INTO checklist_result (run_id, attempt, item_id, score) VALUES ('UC-0001/T1/run-1', 1, 'CHK-1', 1)",
        ):
            conn.execute(text(sql))


def test_tables_and_views(app_engine: Engine) -> None:
    with app_engine.connect() as conn:
        names = table_names(conn)
        default = column_info(conn, "terminal_run")["profile_version"][2]
    assert set(TABLES) | set(VIEWS) <= names
    assert default == "0"


def test_constraints(app_engine: Engine) -> None:
    _seed(app_engine)
    bad = (
        "INSERT INTO content_blob (content_hash, body, size) VALUES ('md5:x', '[]', 2)",
        f"INSERT INTO artifact_version (run_id, artifact_id, version, content_hash, producer_type, producer_id, schema_valid) VALUES ('UC-0001/T1/run-1', 'kpis', 0, '{HASH}', 'agent', 'a', true)",
        f"INSERT INTO artifact_version (run_id, artifact_id, version, content_hash, producer_type, producer_id, schema_valid) VALUES ('UC-0001/T1/run-1', 'kpis', 2, '{HASH}', 'robot', 'a', true)",
        f"INSERT INTO artifact_attachment (run_id, artifact_id, version, content_hash, file_name, media_type, size) VALUES ('UC-0001/T1/run-1', 'kpis', 1, '{HASH}', '../etc/passwd', 'text/plain', 3)",
        "INSERT INTO profile_version (usecase_id, version, profile_values, source_run_id) VALUES ('UC-0001', 0, '{}', 'UC-0001/T1/run-1')",
    )
    with app_engine.connect() as conn:
        for sql in bad:
            with pytest.raises(DBAPIError), conn.begin_nested():
                conn.execute(text(sql))


def test_append_only(app_engine: Engine) -> None:
    _seed(app_engine)
    with app_engine.connect() as conn:
        for table in TABLES:
            with pytest.raises(DBAPIError) as info, conn.begin_nested():
                conn.execute(text(f"DELETE FROM {table}"))
            assert "append-only" in str(info.value.orig), table
        with pytest.raises(DBAPIError), conn.begin_nested():
            conn.execute(text("UPDATE content_blob SET size = 3"))


def test_columns_added_to_existing_tables(owner_engine: Engine) -> None:
    """005 adds run columns for the profile, edits and control re-checks (data-model.md)."""
    with owner_engine.connect() as conn:
        run = column_info(conn, "terminal_run")
        decision = column_info(conn, "policy_decision")
    assert decision["attempt"] == ("integer", False, None)
    assert run["approvals_after_sign_off_id"] == ("bigint", False, None)
    assert run["controls_pending"] == ("boolean", True, "FALSE")
    assert run["profile_version"] == ("integer", True, "0")
