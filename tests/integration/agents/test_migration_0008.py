"""T003: the 008 tables (data-model.md): knowledge retrievals and artifact citations."""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

HASH = "sha256:" + "c" * 64
RUN = "UC-0001/T0/run-1"
TABLES = ("knowledge_retrieval", "artifact_citation")


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
        "INSERT INTO knowledge_retrieval (run_id, attempt, step, source, operation, request, "
        "document, section, content_hash, data_class, synthetic, retrieved_at) VALUES "
        f"('{RUN}', {values['attempt']}, {values['step']}, {values['source']}, "
        f"{values['operation']}, {values['request']}, {values['document']}, {values['section']}, "
        f"{values['hash']}, 'internal', true, now())"
    )


def _seed(engine: Engine) -> None:
    with engine.begin() as conn:
        for sql in (
            "INSERT INTO usecase (usecase_id, name, intake_text, submitted_by) VALUES ('UC-0001', 'n', 'i', 'o')",
            f"INSERT INTO terminal_run (run_id, usecase_id, terminal_id, run_number, spec_version, state, mode, trigger_event_type) VALUES ('{RUN}', 'UC-0001', 'T0', 1, '1.0.0', 'opened', 'evolve', 'usecase.submitted')",
            f"INSERT INTO content_blob (content_hash, body, size) VALUES ('{HASH}', '[]', 2)",
            f"INSERT INTO artifact_version (run_id, artifact_id, version, content_hash, producer_type, producer_id, attempt, schema_valid) VALUES ('{RUN}', 'raci', 1, '{HASH}', 'agent', 't0-intake-agent', 1, true)",
            _retrieval(),
            f"INSERT INTO artifact_citation (run_id, artifact_id, version, row_index, source, document, section, content_hash, knowledge_retrieval_id, cited_at) SELECT '{RUN}', 'raci', 1, 0, 'confluence', 'sops/claims.md', 'Triage', '{HASH}', knowledge_retrieval_id, now() FROM knowledge_retrieval",
        ):
            conn.execute(text(sql))


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
        f"INSERT INTO artifact_citation (run_id, artifact_id, version, source, document, content_hash, knowledge_retrieval_id, cited_at) VALUES ('{RUN}', 'raci', 9, 'confluence', 'd', '{HASH}', 1, now())",
        f"INSERT INTO artifact_citation (run_id, artifact_id, version, source, document, content_hash, knowledge_retrieval_id, cited_at) VALUES ('{RUN}', 'raci', 1, 'confluence', 'd', '{HASH}', 999, now())",
        f"INSERT INTO artifact_citation (run_id, artifact_id, version, row_index, source, document, content_hash, knowledge_retrieval_id, cited_at) SELECT '{RUN}', 'raci', 1, -1, 'confluence', 'd', '{HASH}', knowledge_retrieval_id, now() FROM knowledge_retrieval",
    ]
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
            conn.execute(text("UPDATE artifact_citation SET row_index = 1"))
