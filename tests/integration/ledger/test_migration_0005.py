"""T003: migration 0005 (data-model.md): ledger content, versions, profile, verification, views."""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from tests.support.pg import PlatformDatabase, alembic

HASH = "sha256:" + "a" * 64
TABLES = (
    "ledger.content_blob",
    "ledger.file_object",
    "ledger.profile_version",
    "ledger.verification_run",
    "run.artifact_version",
    "run.artifact_attachment",
    "run.checklist_result",
)
VIEWS = ("run.v_run_step", "run.v_usecase_terminal_summary")


def _seed(engine: Engine) -> None:
    with engine.begin() as conn:
        for sql in (
            "INSERT INTO run.usecase (usecase_id, name, intake_text, submitted_by) VALUES ('UC-0001', 'n', 'i', 'o')",
            "INSERT INTO run.terminal_run (run_id, usecase_id, terminal_id, run_number, spec_version, state, mode, trigger_event_type) VALUES ('UC-0001/T1/run-1', 'UC-0001', 'T1', 1, '1.0.0', 'opened', 'evolve', 'T0.pass')",
            f"INSERT INTO ledger.content_blob (content_hash, body, size) VALUES ('{HASH}', '[]', 2)",
            f"INSERT INTO ledger.file_object (content_hash, size, media_type) VALUES ('{HASH}', 3, 'text/plain')",
            "INSERT INTO ledger.profile_version (usecase_id, version, profile_values, source_run_id) VALUES ('UC-0001', 1, '{}', 'UC-0001/T1/run-1')",
            "INSERT INTO ledger.verification_run (actor, scope, started_at, finished_at, records_checked, breaks, verified) VALUES ('a', 'all', now(), now(), 0, '[]', true)",
            f"INSERT INTO run.artifact_version (run_id, artifact_id, version, content_hash, producer_type, producer_id, schema_valid) VALUES ('UC-0001/T1/run-1', 'kpis', 1, '{HASH}', 'agent', 'agent:x', true)",
            f"INSERT INTO run.artifact_attachment (run_id, artifact_id, version, content_hash, file_name, media_type, size) VALUES ('UC-0001/T1/run-1', 'kpis', 1, '{HASH}', 'a.txt', 'text/plain', 3)",
            "INSERT INTO run.checklist_result (run_id, attempt, item_id, score) VALUES ('UC-0001/T1/run-1', 1, 'CHK-1', 1)",
        ):
            conn.execute(text(sql))


def test_tables_views_and_grants(app_engine: Engine) -> None:
    with app_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_schema || '.' || table_name, privilege_type FROM information_schema.role_table_grants "
                "WHERE grantee = current_user"
            )
        ).all()
        default = conn.execute(
            text(
                "SELECT column_default FROM information_schema.columns WHERE table_name = 'terminal_run' AND column_name = 'profile_version'"
            )
        ).scalar_one()
    grants: dict[str, set[str]] = {}
    for table, privilege in rows:
        grants.setdefault(table, set()).add(privilege)
    for table in TABLES:
        assert grants[table] == {"SELECT", "INSERT"}, table
    for view in VIEWS:
        assert grants[view] == {"SELECT"}, view
    assert default == "0"


def test_constraints(app_engine: Engine) -> None:
    _seed(app_engine)
    bad = (
        "INSERT INTO ledger.content_blob (content_hash, body, size) VALUES ('md5:x', '[]', 2)",
        f"INSERT INTO run.artifact_version (run_id, artifact_id, version, content_hash, producer_type, producer_id, schema_valid) VALUES ('UC-0001/T1/run-1', 'kpis', 0, '{HASH}', 'agent', 'a', true)",
        f"INSERT INTO run.artifact_version (run_id, artifact_id, version, content_hash, producer_type, producer_id, schema_valid) VALUES ('UC-0001/T1/run-1', 'kpis', 2, '{HASH}', 'robot', 'a', true)",
        f"INSERT INTO run.artifact_attachment (run_id, artifact_id, version, content_hash, file_name, media_type, size) VALUES ('UC-0001/T1/run-1', 'kpis', 1, '{HASH}', '../etc/passwd', 'text/plain', 3)",
        "INSERT INTO ledger.profile_version (usecase_id, version, profile_values, source_run_id) VALUES ('UC-0001', 0, '{}', 'UC-0001/T1/run-1')",
    )
    with app_engine.connect() as conn:
        for sql in bad:
            with pytest.raises(DBAPIError), conn.begin_nested():
                conn.execute(text(sql))


def test_append_only(app_engine: Engine, owner_engine: Engine) -> None:
    _seed(app_engine)
    for engine in (app_engine, owner_engine):
        with engine.connect() as conn:
            for table in TABLES:
                for sql in (f"DELETE FROM {table}", f"TRUNCATE {table} CASCADE"):
                    with pytest.raises(DBAPIError), conn.begin_nested():
                        conn.execute(text(sql))
            with pytest.raises(DBAPIError), conn.begin_nested():
                conn.execute(text("UPDATE ledger.content_blob SET size = 3"))


def test_round_trip(migrated_db: PlatformDatabase) -> None:
    alembic(migrated_db, "downgrade", "0004")
    alembic(migrated_db, "upgrade", "head")
