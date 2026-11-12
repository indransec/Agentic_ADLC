"""T003: migration 0009 (data-model.md): tool calls, evidence results, enterprise records."""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from tests.support.pg import PlatformDatabase, alembic

HASH = "sha256:" + "d" * 64
TABLES = ("tools.tool_call", "tools.tool_result", "tools.enterprise_record")


def _call(**over: str) -> str:
    values = {
        "attempt": "1",
        "tool": "'pilot_env_create'",
        "server": "'pilot_env'",
        "scope": "'dev'",
        "hash": f"'{HASH}'",
        "outcome": "'ok'",
        "reason": "''",
    }
    values.update(over)
    return (
        "INSERT INTO tools.tool_call (run_id, usecase_id, terminal_id, attempt, step, tool, server, "
        "scope, arguments_sha256, outcome, reason, duration_ms, at) VALUES ('UC-0001/T3/run-1', "
        f"'UC-0001', 'T3', {values['attempt']}, 1, {values['tool']}, {values['server']}, "
        f"{values['scope']}, {values['hash']}, {values['outcome']}, {values['reason']}, 12, now())"
    )


def _result(kind: str = "'ci'", package: str = f"'{HASH}'") -> str:
    return (
        "INSERT INTO tools.tool_result (tool_call_id, run_id, usecase_id, terminal_id, kind, "
        f"package_hash, result, result_sha256, at) SELECT tool_call_id, run_id, usecase_id, "
        f"terminal_id, {kind}, {package}, '{{}}', '{HASH}', now() FROM tools.tool_call LIMIT 1"
    )


def _record(system: str = "'servicenow'", record_id: str = "'CHG-1'", version: str = "1") -> str:
    return (
        "INSERT INTO tools.enterprise_record (system, kind, record_id, version, usecase_id, run_id, "
        f"terminal_id, body, at) VALUES ({system}, 'change', {record_id}, {version}, 'UC-0001', "
        "'UC-0001/T6/run-1', 'T6', '{}', now())"
    )


def _seed(engine: Engine) -> None:
    with engine.begin() as conn:
        for sql in (_call(), _result(), _record()):
            conn.execute(text(sql))


def test_grants(app_engine: Engine) -> None:
    with app_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_schema || '.' || table_name, privilege_type FROM "
                "information_schema.role_table_grants WHERE grantee = current_user"
            )
        ).all()
    grants: dict[str, set[str]] = {}
    for table, privilege in rows:
        grants.setdefault(table, set()).add(privilege)
    for table in TABLES:
        assert grants[table] == {"SELECT", "INSERT"}, table


def test_constraints(app_engine: Engine) -> None:
    _seed(app_engine)
    bad = [
        _call(attempt="0"),
        _call(tool="'Pilot-Env'"),
        _call(hash="'md5:x'"),
        _call(outcome="'maybe'"),
        _call(outcome="'refused'"),  # a refusal needs a reason
        _result(kind="'other'"),
        _result(package="'sha256:short'"),
        _record(system="'jira'"),
        _record(record_id="'chg-1'"),
        _record(version="0"),
        _record(),  # the same system, record and version twice
    ]
    with app_engine.connect() as conn:
        for sql in bad:
            with pytest.raises(DBAPIError), conn.begin_nested():
                conn.execute(text(sql))
        conn.execute(text(_record(version="2")))  # a new version is fine


def test_append_only(app_engine: Engine, owner_engine: Engine) -> None:
    _seed(app_engine)
    for engine in (app_engine, owner_engine):
        with engine.connect() as conn:
            for table in TABLES:
                for sql in (f"DELETE FROM {table}", f"TRUNCATE {table} CASCADE"):
                    with pytest.raises(DBAPIError), conn.begin_nested():
                        conn.execute(text(sql))
            with pytest.raises(DBAPIError), conn.begin_nested():
                conn.execute(text("UPDATE tools.tool_call SET reason = 'x'"))


def test_round_trip(migrated_db: PlatformDatabase) -> None:
    alembic(migrated_db, "downgrade", "0008")
    alembic(migrated_db, "upgrade", "head")
