"""Evidence ledger: content store, artifact versions, profile, verification, views (005 data-model.md).

Every new table is append-only for every identity (reusing ``run.reject_mutation()`` from 0003).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-10
"""

from typing import Any

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None

HASH = "^sha256:[0-9a-f]{64}$"
TABLES = (
    "ledger.content_blob",
    "ledger.file_object",
    "ledger.profile_version",
    "ledger.verification_run",
    "run.artifact_version",
    "run.artifact_attachment",
    "run.checklist_result",
)
SEQUENCES = (
    "ledger.verification_run_verification_run_id_seq",
    "run.checklist_result_checklist_result_id_seq",
)
VIEWS = ("run.v_run_step", "run.v_usecase_terminal_summary")
AUTOMATIC = "('opened', 'building', 'checking', 'reviewing')"
WAITING = "('awaiting_clarification', 'awaiting_sign_off', 'escalated')"


def _app(kwargs: dict[str, Any]) -> str:
    role = kwargs.get("app_role")
    if not isinstance(role, str) or not role:
        raise RuntimeError("app_role not supplied by env.py")
    return str(op.get_context().dialect.identifier_preparer.quote(role))


def upgrade(**kwargs: Any) -> None:
    app = _app(kwargs)
    op.execute(
        f"""
        CREATE TABLE ledger.content_blob (
            content_hash text PRIMARY KEY CHECK (content_hash ~ '{HASH}'),
            body jsonb NOT NULL,
            size integer NOT NULL CHECK (size >= 0),
            stored_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE ledger.file_object (
            content_hash text PRIMARY KEY CHECK (content_hash ~ '{HASH}'),
            size bigint NOT NULL CHECK (size >= 0),
            media_type text NOT NULL,
            stored_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE ledger.profile_version (
            usecase_id text NOT NULL REFERENCES run.usecase (usecase_id),
            version integer NOT NULL CHECK (version >= 1),
            profile_values jsonb NOT NULL,
            source_run_id text NOT NULL REFERENCES run.terminal_run (run_id),
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (usecase_id, version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE ledger.verification_run (
            verification_run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            actor text NOT NULL,
            scope text NOT NULL,
            started_at timestamptz NOT NULL,
            finished_at timestamptz NOT NULL,
            records_checked integer NOT NULL,
            breaks jsonb NOT NULL,
            verified boolean NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE run.artifact_version (
            run_id text NOT NULL REFERENCES run.terminal_run (run_id),
            artifact_id text NOT NULL,
            version integer NOT NULL CHECK (version >= 1),
            content_hash text NOT NULL REFERENCES ledger.content_blob (content_hash),
            producer_type text NOT NULL CHECK (producer_type IN ('agent', 'person')),
            producer_id text NOT NULL,
            attempt integer NULL,
            derived_from_version integer NULL,
            schema_valid boolean NOT NULL,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (run_id, artifact_id, version)
        )
        """
    )
    op.execute(
        r"""
        CREATE TABLE run.artifact_attachment (
            run_id text NOT NULL,
            artifact_id text NOT NULL,
            version integer NOT NULL,
            content_hash text NOT NULL REFERENCES ledger.file_object (content_hash),
            file_name text NOT NULL CHECK (length(file_name) BETWEEN 1 AND 255
                AND file_name !~ '[/\\]'),
            media_type text NOT NULL,
            size bigint NOT NULL,
            PRIMARY KEY (run_id, artifact_id, version, content_hash),
            FOREIGN KEY (run_id, artifact_id, version)
                REFERENCES run.artifact_version (run_id, artifact_id, version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE run.checklist_result (
            checklist_result_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            run_id text NOT NULL REFERENCES run.terminal_run (run_id),
            attempt integer NOT NULL,
            item_id text NOT NULL,
            score integer NULL,
            finding text NULL,
            recorded_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("ALTER TABLE run.terminal_run ADD COLUMN profile_version integer NOT NULL DEFAULT 0")
    op.execute(
        """
        CREATE VIEW run.v_run_step AS
        SELECT run_id, step, actor_type, actor_id, started_at, ended_at,
               EXTRACT(EPOCH FROM (ended_at - started_at)) AS duration_seconds, outcome,
               run_activity_id
        FROM run.run_activity
        """
    )
    op.execute(
        f"""
        CREATE VIEW run.v_usecase_terminal_summary AS
        WITH spans AS (
            SELECT t.run_id, t.to_state,
                   COALESCE(LEAD(t.at) OVER (PARTITION BY t.run_id ORDER BY t.at, t.run_transition_id),
                            CASE WHEN t.to_state = 'closed' THEN t.at ELSE now() END) - t.at AS spent
            FROM run.run_transition t
        ),
        per_run AS (
            SELECT r.usecase_id, r.terminal_id, r.run_id, r.rework_count, r.clarification_rounds,
                   r.escalation_trigger,
                   COALESCE(SUM(EXTRACT(EPOCH FROM s.spent)) FILTER (WHERE s.to_state IN {AUTOMATIC}), 0) AS automatic_seconds,
                   COALESCE(SUM(EXTRACT(EPOCH FROM s.spent)) FILTER (WHERE s.to_state IN {WAITING}), 0) AS waiting_seconds
            FROM run.terminal_run r LEFT JOIN spans s USING (run_id)
            GROUP BY r.usecase_id, r.terminal_id, r.run_id, r.rework_count, r.clarification_rounds,
                     r.escalation_trigger
        )
        SELECT usecase_id, terminal_id,
               count(*) AS runs,
               count(*) FILTER (WHERE rework_count > 0) AS reworks,
               COALESCE(SUM(clarification_rounds), 0) AS clarification_rounds,
               count(*) FILTER (WHERE escalation_trigger IS NOT NULL) AS escalations,
               COALESCE(SUM(automatic_seconds), 0) AS automatic_seconds,
               COALESCE(SUM(waiting_seconds), 0) AS waiting_seconds
        FROM per_run GROUP BY usecase_id, terminal_id
        """
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
    for view in VIEWS:
        op.execute(f"REVOKE ALL ON {view} FROM PUBLIC")
        op.execute(f"GRANT SELECT ON {view} TO {app}")


def downgrade(**kwargs: Any) -> None:
    for view in reversed(VIEWS):
        op.execute(f"DROP VIEW {view}")
    op.execute("ALTER TABLE run.terminal_run DROP COLUMN profile_version")
    for table in (
        "run.checklist_result",
        "run.artifact_attachment",
        "run.artifact_version",
        "ledger.verification_run",
        "ledger.profile_version",
        "ledger.file_object",
        "ledger.content_blob",
    ):
        op.execute(f"DROP TABLE {table}")
