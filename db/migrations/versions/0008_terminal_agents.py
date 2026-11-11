"""Terminal agents T0-T2: knowledge retrievals and artifact citations (008, data-model.md).

Both tables are append-only for every identity (``run.reject_mutation()``, as features 003, 005
and 006 use).

Revision ID: 0008
Revises: 0006
Create Date: 2026-11-11
"""

from typing import Any

from alembic import op

revision: str = "0008"
down_revision: str | None = "0006"
branch_labels: str | None = None
depends_on: str | None = None

HASH = "^sha256:[0-9a-f]{64}$"
SOURCE = "^[a-z][a-z0-9]*(_[a-z0-9]+)*$"
TABLES = ("run.knowledge_retrieval", "run.artifact_citation")
SEQUENCES = (
    "run.knowledge_retrieval_knowledge_retrieval_id_seq",
    "run.artifact_citation_artifact_citation_id_seq",
)


def _app(kwargs: dict[str, Any]) -> str:
    role = kwargs.get("app_role")
    if not isinstance(role, str) or not role:
        raise RuntimeError("app_role not supplied by env.py")
    return str(op.get_context().dialect.identifier_preparer.quote(role))


def upgrade(**kwargs: Any) -> None:
    app = _app(kwargs)
    op.execute(
        f"""
        CREATE TABLE run.knowledge_retrieval (
            knowledge_retrieval_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            run_id text NOT NULL REFERENCES run.terminal_run (run_id),
            attempt integer NOT NULL CHECK (attempt >= 1),
            step integer NOT NULL CHECK (step >= 0),
            source text NOT NULL CHECK (source ~ '{SOURCE}'),
            operation text NOT NULL CHECK (operation IN ('search', 'read')),
            request text NOT NULL CHECK (length(request) <= 500),
            document text NOT NULL CHECK (length(document) BETWEEN 1 AND 500),
            section text NOT NULL DEFAULT '' CHECK (length(section) <= 500),
            content_hash text NOT NULL CHECK (content_hash ~ '{HASH}'),
            data_class text NOT NULL,
            synthetic boolean NOT NULL,
            retrieved_at timestamptz NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX knowledge_retrieval_by_attempt ON run.knowledge_retrieval (run_id, attempt)"
    )
    op.execute(
        f"""
        CREATE TABLE run.artifact_citation (
            artifact_citation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            run_id text NOT NULL,
            artifact_id text NOT NULL,
            version integer NOT NULL,
            row_index integer NULL CHECK (row_index IS NULL OR row_index >= 0),
            source text NOT NULL CHECK (source ~ '{SOURCE}'),
            document text NOT NULL,
            section text NOT NULL DEFAULT '',
            content_hash text NOT NULL CHECK (content_hash ~ '{HASH}'),
            knowledge_retrieval_id bigint NOT NULL
                REFERENCES run.knowledge_retrieval (knowledge_retrieval_id),
            cited_at timestamptz NOT NULL,
            FOREIGN KEY (run_id, artifact_id, version)
                REFERENCES run.artifact_version (run_id, artifact_id, version)
        )
        """
    )
    op.execute(
        "CREATE INDEX artifact_citation_by_version ON run.artifact_citation "
        "(run_id, artifact_id, version)"
    )
    for table in TABLES:
        name = table.replace(".", "_")
        op.execute(
            f"CREATE TRIGGER {name}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION run.reject_mutation()"
        )
        op.execute(
            f"CREATE TRIGGER {name}_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION run.reject_mutation()"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        op.execute(f"GRANT SELECT, INSERT ON {table} TO {app}")
    for sequence in SEQUENCES:
        op.execute(f"GRANT USAGE ON SEQUENCE {sequence} TO {app}")


def downgrade(**kwargs: Any) -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE {table}")
