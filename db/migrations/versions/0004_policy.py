"""Policy engine: decision log and frozen parameter sets (004 data-model.md).

Both tables are append-only for every identity; they reuse ``run.reject_mutation()`` from 0003.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-10
"""

from typing import Any

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None

TABLES = ("run.policy_decision", "run.run_parameter_set")


def _app(kwargs: dict[str, Any]) -> str:
    role = kwargs.get("app_role")
    if not isinstance(role, str) or not role:
        raise RuntimeError("app_role not supplied by env.py")
    return str(op.get_context().dialect.identifier_preparer.quote(role))


def upgrade(**kwargs: Any) -> None:
    app = _app(kwargs)
    op.execute(
        """
        CREATE TABLE run.policy_decision (
            policy_decision_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            kind text NOT NULL CHECK (kind IN ('evaluate', 'authorize')),
            run_id text NULL,
            usecase_id text NULL,
            terminal_id text NULL,
            check_id text NOT NULL,
            rule text NOT NULL,
            actor text NULL,
            passed boolean NOT NULL,
            value jsonb NULL,
            reason text NOT NULL CHECK (length(reason) <= 2000),
            inputs jsonb NOT NULL,
            synthetic boolean NOT NULL,
            fail_safe boolean NOT NULL,
            duration_ms numeric NOT NULL,
            decided_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
        """
    )
    op.execute(
        "CREATE INDEX policy_decision_by_run ON run.policy_decision "
        "(run_id, decided_at, policy_decision_id)"
    )
    op.execute(
        """
        CREATE TABLE run.run_parameter_set (
            run_id text PRIMARY KEY REFERENCES run.terminal_run (run_id),
            risk_tier text NOT NULL CHECK (risk_tier IN ('low', 'medium', 'high')),
            guardrail_version text NOT NULL,
            parameters jsonb NOT NULL,
            rejected jsonb NOT NULL,
            resolved_at timestamptz NOT NULL DEFAULT now()
        )
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
    op.execute(f"GRANT USAGE ON SEQUENCE run.policy_decision_policy_decision_id_seq TO {app}")


def downgrade(**kwargs: Any) -> None:
    op.execute("DROP TABLE run.run_parameter_set")
    op.execute("DROP TABLE run.policy_decision")
