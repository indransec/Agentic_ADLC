"""MCP tools: tool calls, evidence results and the enterprise mocks' records (010, data-model.md).

All three tables are append-only for every identity (``run.reject_mutation()``, as features 003,
005, 006 and 008 use). A mock record changes by a new version; the highest version is current.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-12
"""

from typing import Any

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | None = None
depends_on: str | None = None

HASH = "^sha256:[0-9a-f]{64}$"
NAME = "^[a-z][a-z0-9]*(_[a-z0-9]+)*$"
TABLES = ("tools.tool_call", "tools.tool_result", "tools.enterprise_record")
SEQUENCES = (
    "tools.tool_call_tool_call_id_seq",
    "tools.tool_result_tool_result_id_seq",
    "tools.enterprise_record_enterprise_record_id_seq",
)
OUTCOMES = ("ok", "refused", "failed", "timed_out", "unavailable")
RESULT_KINDS = (
    "ci",
    "harness",
    "redteam",
    "dlp",
    "deploy",
    "traffic",
    "kill_switch",
    "environment",
)
SYSTEMS = ("servicenow", "cmdb", "agent_registry", "iam", "grc", "eval_store")
RECORD_KINDS = ("change", "incident", "ci", "agent", "revocation", "report", "note")


def _app(kwargs: dict[str, Any]) -> str:
    role = kwargs.get("app_role")
    if not isinstance(role, str) or not role:
        raise RuntimeError("app_role not supplied by env.py")
    return str(op.get_context().dialect.identifier_preparer.quote(role))


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade(**kwargs: Any) -> None:
    app = _app(kwargs)
    op.execute("CREATE SCHEMA tools")
    op.execute(f"GRANT USAGE ON SCHEMA tools TO {app}")
    op.execute(
        f"""
        CREATE TABLE tools.tool_call (
            tool_call_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            run_id text NOT NULL,
            usecase_id text NOT NULL,
            terminal_id text NOT NULL,
            attempt integer NOT NULL CHECK (attempt >= 1),
            step integer NOT NULL CHECK (step >= 0),
            tool text NOT NULL CHECK (tool ~ '{NAME}'),
            server text NOT NULL CHECK (server ~ '{NAME}'),
            scope text NOT NULL CHECK (scope ~ '{NAME}'),
            arguments_sha256 text NOT NULL CHECK (arguments_sha256 ~ '{HASH}'),
            outcome text NOT NULL CHECK (outcome IN ({_in(OUTCOMES)})),
            reason text NOT NULL DEFAULT '' CHECK (length(reason) <= 2000),
            duration_ms integer NOT NULL CHECK (duration_ms >= 0),
            at timestamptz NOT NULL,
            CHECK (outcome = 'ok' OR reason <> '')
        )
        """
    )
    op.execute("CREATE INDEX tool_call_by_run ON tools.tool_call (run_id, attempt)")
    op.execute(
        f"""
        CREATE TABLE tools.tool_result (
            tool_result_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tool_call_id bigint NOT NULL REFERENCES tools.tool_call (tool_call_id),
            run_id text NOT NULL,
            usecase_id text NOT NULL,
            terminal_id text NOT NULL,
            kind text NOT NULL CHECK (kind IN ({_in(RESULT_KINDS)})),
            package_hash text NULL CHECK (package_hash IS NULL OR package_hash ~ '{HASH}'),
            result jsonb NOT NULL,
            result_sha256 text NOT NULL CHECK (result_sha256 ~ '{HASH}'),
            at timestamptz NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX tool_result_by_usecase ON tools.tool_result (usecase_id, kind)")
    op.execute(
        f"""
        CREATE TABLE tools.enterprise_record (
            enterprise_record_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            system text NOT NULL CHECK (system IN ({_in(SYSTEMS)})),
            kind text NOT NULL CHECK (kind IN ({_in(RECORD_KINDS)})),
            record_id text NOT NULL CHECK (record_id ~ '^[A-Z]+-[0-9]+$'),
            version integer NOT NULL CHECK (version >= 1),
            usecase_id text NOT NULL,
            run_id text NOT NULL,
            terminal_id text NOT NULL,
            body jsonb NOT NULL,
            at timestamptz NOT NULL,
            UNIQUE (system, record_id, version)
        )
        """
    )
    op.execute(
        "CREATE INDEX enterprise_record_by_usecase ON tools.enterprise_record (usecase_id, system)"
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
    op.execute("DROP SCHEMA tools")
