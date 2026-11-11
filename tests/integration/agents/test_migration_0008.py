"""T003: migration 0008 (data-model.md): knowledge retrievals and artifact citations."""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from tests.support.pg import PlatformDatabase, alembic

HASH = "sha256:" + "c" * 64
RUN = "UC-0001/T0/run-1"
TABLES = ("run.knowledge_retrieval", "run.artifact_citation")


def _retrieval(**over: str) -> str:
    values = {
        "attempt": "1",
        "step": "2",
        "source": "'confluence'",
        "operation": "'search'",
        "request": "'claims'",
        "document": "'sops/claims.md'",
        "section": "'Triage'",
        "hash": f"'{HASH}'",
    }
    values.update(over)
    return (
        "INSERT INTO run.knowledge_retrieval (run_id, attempt, step, source, operation, request, "
        "document, section, content_hash, data_class, synthetic, retrieved_at) VALUES "
        f"('{RUN}', {values['attempt']}, {values['step']}, {values['source']}, "
        f"{values['operation']}, {values['request']}, {values['document']}, {values['section']}, "
        f"{values['hash']}, 'internal', true, now())"
    )


def _seed(engine: Engine) -> None:
    with engine.begin() as conn:
        for sql in (
            "INSERT INTO run.usecase (usecase_id, name, intake_text, submitted_by) VALUES ('UC-0001', 'n', 'i', 'o')",
            f"INSERT INTO run.terminal_run (run_id, usecase_id, terminal_id, run_number, spec_version, state, mode, trigger_event_type) VALUES ('{RUN}', 'UC-0001', 'T0', 1, '1.0.0', 'opened', 'evolve', 'usecase.submitted')",
            f"INSERT INTO ledger.content_blob (content_hash, body, size) VALUES ('{HASH}', '[]', 2)",
            f"INSERT INTO run.artifact_version (run_id, artifact_id, version, content_hash, producer_type, producer_id, attempt, schema_valid) VALUES ('{RUN}', 'raci', 1, '{HASH}', 'agent', 't0-intake-agent', 1, true)",
            _retrieval(),
            f"INSERT INTO run.artifact_citation (run_id, artifact_id, version, row_index, source, document, section, content_hash, knowledge_retrieval_id, cited_at) SELECT '{RUN}', 'raci', 1, 0, 'confluence', 'sops/claims.md', 'Triage', '{HASH}', knowledge_retrieval_id, now() FROM run.knowledge_retrieval",
        ):
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
        _retrieval(attempt="0"),
        _retrieval(step="-1"),
        _retrieval(source="'Confluence'"),
        _retrieval(operation="'write'"),
        _retrieval(request="'" + "q" * 501 + "'"),
        _retrieval(document="''"),
        _retrieval(hash="'md5:x'"),
        # a citation must point to an existing artifact version and retrieval
        f"INSERT INTO run.artifact_citation (run_id, artifact_id, version, source, document, content_hash, knowledge_retrieval_id, cited_at) VALUES ('{RUN}', 'raci', 9, 'confluence', 'd', '{HASH}', 1, now())",
        f"INSERT INTO run.artifact_citation (run_id, artifact_id, version, source, document, content_hash, knowledge_retrieval_id, cited_at) VALUES ('{RUN}', 'raci', 1, 'confluence', 'd', '{HASH}', 999, now())",
        f"INSERT INTO run.artifact_citation (run_id, artifact_id, version, row_index, source, document, content_hash, knowledge_retrieval_id, cited_at) SELECT '{RUN}', 'raci', 1, -1, 'confluence', 'd', '{HASH}', knowledge_retrieval_id, now() FROM run.knowledge_retrieval",
    ]
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
                conn.execute(text("UPDATE run.artifact_citation SET row_index = 1"))


def test_round_trip(migrated_db: PlatformDatabase) -> None:
    alembic(migrated_db, "downgrade", "0006")
    alembic(migrated_db, "upgrade", "head")
