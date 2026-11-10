"""Agent runtime: prompt registry, agent attempts, model calls, cost alerts, cost views (006).

Every new table is append-only for every identity: ``spec.prompt_registry`` reuses
``spec.reject_mutation()`` (as the playbook registry does), the ``run`` tables reuse
``run.reject_mutation()``.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-10
"""

from typing import Any

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | None = None
depends_on: str | None = None

HASH = "^sha256:[0-9a-f]{64}$"
SEMVER = r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
RUN_TABLES = ("run.agent_attempt", "run.model_call", "run.cost_alert")
SEQUENCES = (
    "run.agent_attempt_agent_attempt_id_seq",
    "run.model_call_model_call_id_seq",
    "run.cost_alert_cost_alert_id_seq",
)
VIEWS = ("run.v_run_cost", "run.v_terminal_cost", "run.v_usecase_cost")
TRIGGERS_0003 = (
    "rework_limit",
    "timer",
    "clarification_limit",
    "clarification_sla",
    "retry_limit",
    "budget",
)
TRIGGERS_0006 = (*TRIGGERS_0003, "model_unavailable", "reviewer_failed")
COST_TOTALS = """
    count(*) FILTER (WHERE outcome = 'ok') AS calls,
    COALESCE(SUM(tokens_in), 0) AS tokens_in,
    COALESCE(SUM(tokens_out), 0) AS tokens_out,
    COALESCE(SUM(cost_usd) FILTER (WHERE cost_known), 0) AS cost_usd,
    count(*) FILTER (WHERE NOT cost_known AND outcome = 'ok') AS unknown_cost_calls,
    count(*) FILTER (WHERE fallback AND outcome = 'ok') AS fallback_answers
"""


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _app(kwargs: dict[str, Any]) -> str:
    role = kwargs.get("app_role")
    if not isinstance(role, str) or not role:
        raise RuntimeError("app_role not supplied by env.py")
    return str(op.get_context().dialect.identifier_preparer.quote(role))


def _triggers(values: tuple[str, ...]) -> None:
    op.execute("ALTER TABLE run.terminal_run DROP CONSTRAINT terminal_run_escalation_trigger_check")
    op.execute(
        "ALTER TABLE run.terminal_run ADD CONSTRAINT terminal_run_escalation_trigger_check "
        f"CHECK (escalation_trigger IN ({_in(values)}))"
    )


def upgrade(**kwargs: Any) -> None:
    app = _app(kwargs)
    op.execute(
        f"""
        CREATE TABLE spec.prompt_registry (
            prompt_registry_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            prompt_id text NOT NULL CHECK (prompt_id ~ '^[a-z][a-z0-9]*(-[a-z0-9]+)*$'),
            version text NOT NULL CHECK (version ~ '{SEMVER}'),
            path text NOT NULL,
            content_hash text NOT NULL CHECK (content_hash ~ '{HASH}'),
            registered_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (prompt_id, version)
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE run.agent_attempt (
            agent_attempt_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            run_id text NOT NULL REFERENCES run.terminal_run (run_id),
            kind text NOT NULL CHECK (kind IN ('build', 'review')),
            attempt integer NOT NULL CHECK (attempt >= 1),
            agent_id text NOT NULL,
            agent_version text NOT NULL,
            implementation text NOT NULL CHECK (implementation IN ('stub', 'model')),
            prompt_hash text NULL CHECK (prompt_hash IS NULL OR prompt_hash ~ '{HASH}'),
            playbook_hashes jsonb NOT NULL DEFAULT '{{}}',
            context_hash text NOT NULL CHECK (context_hash ~ '{HASH}'),
            steps integer NOT NULL CHECK (steps >= 0),
            tokens_in integer NOT NULL CHECK (tokens_in >= 0),
            tokens_out integer NOT NULL CHECK (tokens_out >= 0),
            cost_usd numeric(14, 6) NULL CHECK (cost_usd IS NULL OR cost_usd >= 0),
            corrections integer NOT NULL CHECK (corrections >= 0),
            outcome text NOT NULL CHECK (outcome IN ('artifacts', 'clarification',
                'recommendation', 'budget_exceeded', 'failed', 'model_unavailable')),
            limit_reached text NULL CHECK (limit_reached IN ('steps', 'tokens', 'timeout')),
            reason text NULL CHECK (length(reason) <= 2000),
            started_at timestamptz NOT NULL,
            ended_at timestamptz NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX agent_attempt_by_run ON run.agent_attempt (run_id, agent_attempt_id)")
    op.execute(
        f"""
        CREATE TABLE run.model_call (
            model_call_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            agent_attempt_ref text NOT NULL,
            run_id text NOT NULL REFERENCES run.terminal_run (run_id),
            usecase_id text NOT NULL,
            terminal_id text NOT NULL,
            agent_id text NOT NULL,
            tier text NOT NULL,
            entry_index integer NOT NULL CHECK (entry_index >= 1),
            provider text NOT NULL,
            model text NOT NULL,
            prompt_hash text NULL CHECK (prompt_hash IS NULL OR prompt_hash ~ '{HASH}'),
            context_hash text NOT NULL CHECK (context_hash ~ '{HASH}'),
            tokens_in integer NOT NULL CHECK (tokens_in >= 0),
            tokens_out integer NOT NULL CHECK (tokens_out >= 0),
            usage_estimated boolean NOT NULL,
            cost_usd numeric(14, 6) NULL CHECK (cost_usd IS NULL OR cost_usd >= 0),
            cost_known boolean NOT NULL,
            latency_ms numeric NOT NULL CHECK (latency_ms >= 0),
            outcome text NOT NULL CHECK (outcome IN ('ok', 'outage', 'refusal', 'truncated',
                'request_error', 'skipped')),
            reason text NULL CHECK (length(reason) <= 200),
            fallback boolean NOT NULL,
            tried jsonb NOT NULL DEFAULT '[]',
            called_at timestamptz NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX model_call_by_run ON run.model_call (run_id, model_call_id)")
    op.execute("CREATE INDEX model_call_by_usecase ON run.model_call (usecase_id)")
    op.execute(
        """
        CREATE TABLE run.cost_alert (
            cost_alert_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            usecase_id text NOT NULL,
            level_usd numeric(14, 2) NOT NULL CHECK (level_usd > 0),
            total_usd numeric(14, 6) NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (usecase_id, level_usd)
        )
        """
    )
    op.execute("ALTER TABLE run.terminal_run ADD COLUMN model_unavailable_since timestamptz NULL")
    _triggers(TRIGGERS_0006)
    op.execute(
        f"CREATE VIEW run.v_run_cost AS SELECT run_id, usecase_id, terminal_id, {COST_TOTALS} "
        "FROM run.model_call GROUP BY run_id, usecase_id, terminal_id"
    )
    op.execute(
        f"CREATE VIEW run.v_terminal_cost AS SELECT usecase_id, terminal_id, {COST_TOTALS} "
        "FROM run.model_call GROUP BY usecase_id, terminal_id"
    )
    op.execute(
        f"CREATE VIEW run.v_usecase_cost AS SELECT usecase_id, {COST_TOTALS} "
        "FROM run.model_call GROUP BY usecase_id"
    )
    op.execute(
        "CREATE TRIGGER prompt_registry_no_change BEFORE UPDATE OR DELETE ON spec.prompt_registry "
        "FOR EACH ROW EXECUTE FUNCTION spec.reject_mutation()"
    )
    op.execute(
        "CREATE TRIGGER prompt_registry_no_truncate BEFORE TRUNCATE ON spec.prompt_registry "
        "FOR EACH STATEMENT EXECUTE FUNCTION spec.reject_mutation()"
    )
    op.execute("REVOKE ALL ON spec.prompt_registry FROM PUBLIC")
    op.execute(f"GRANT SELECT ON spec.prompt_registry TO {app}")
    for table in RUN_TABLES:
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
    op.execute(
        "UPDATE run.terminal_run SET escalation_trigger = NULL WHERE escalation_trigger IN "
        "('model_unavailable', 'reviewer_failed')"
    )
    _triggers(TRIGGERS_0003)
    op.execute("ALTER TABLE run.terminal_run DROP COLUMN model_unavailable_since")
    for table in ("run.cost_alert", "run.model_call", "run.agent_attempt", "spec.prompt_registry"):
        op.execute(f"DROP TABLE {table}")
