"""Spec registry, catalogues, playbooks, projections and use-case pins (feature 002).

data-model.md (002); FR-019 to FR-023; research R-11. Every table is append-only for every
identity; registry and catalogue rows may only change status along
active → deprecated → retired (and active → retired), and a pinned version cannot be retired.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-10
"""

from typing import Any

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None

HASH = "'^sha256:[0-9a-f]{64}$'"
SEMVER = "'^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$'"
STATUS = "status IN ('active', 'deprecated', 'retired')"

APPEND_ONLY = (
    "playbook_registry",
    "spec_trigger",
    "spec_outcome_route",
    "spec_event_route",
    "spec_change_class",
    "spec_timeline",
)
STATUS_TABLES = ("spec_registry", "spec_catalogue")
ALL_TABLES = (*STATUS_TABLES, *APPEND_ONLY, "usecase_spec_pin")


def _app(kwargs: dict[str, Any]) -> str:
    role = kwargs.get("app_role")
    if not isinstance(role, str) or not role:
        raise RuntimeError("app_role not supplied by env.py")
    return str(op.get_context().dialect.identifier_preparer.quote(role))


def upgrade(**kwargs: Any) -> None:
    app = _app(kwargs)
    op.execute(
        f"""
        CREATE TABLE spec.spec_registry (
            spec_registry_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            terminal_id text NOT NULL CHECK (terminal_id ~ '^T[0-9]+$'),
            version text NOT NULL CHECK (version ~ {SEMVER}),
            status text NOT NULL CHECK ({STATUS}),
            schema_version text NOT NULL,
            spec_yaml text NOT NULL,
            spec_json jsonb NOT NULL,
            content_hash text NOT NULL CHECK (content_hash ~ {HASH}),
            trigger_events text[] NOT NULL,
            emitted_events text[] NOT NULL,
            registered_at timestamptz NOT NULL DEFAULT now(),
            deprecated_at timestamptz NULL,
            retired_at timestamptz NULL,
            UNIQUE (terminal_id, version)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX spec_registry_one_active ON spec.spec_registry (terminal_id) "
        "WHERE status = 'active'"
    )
    op.execute(
        f"""
        CREATE TABLE spec.spec_catalogue (
            spec_catalogue_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            catalogue_name text NOT NULL CHECK (catalogue_name ~ '^[a-z][a-z0-9_]*$'),
            version text NOT NULL CHECK (version ~ {SEMVER}),
            status text NOT NULL CHECK ({STATUS}),
            content_json jsonb NOT NULL,
            content_hash text NOT NULL CHECK (content_hash ~ {HASH}),
            registered_at timestamptz NOT NULL DEFAULT now(),
            deprecated_at timestamptz NULL,
            retired_at timestamptz NULL,
            UNIQUE (catalogue_name, version)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX spec_catalogue_one_active ON spec.spec_catalogue (catalogue_name) "
        "WHERE status = 'active'"
    )
    op.execute(
        f"""
        CREATE TABLE spec.playbook_registry (
            playbook_registry_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            playbook_id text NOT NULL CHECK (playbook_id ~ '^PB-(T[0-9]+|SH)-[0-9]{{2}}$'),
            version text NOT NULL CHECK (version ~ {SEMVER}),
            path text NOT NULL,
            content_hash text NOT NULL CHECK (content_hash ~ {HASH}),
            registered_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (playbook_id, version)
        )
        """
    )
    ref = "spec_registry_id bigint NOT NULL REFERENCES spec.spec_registry (spec_registry_id)"
    op.execute(
        f"""
        CREATE TABLE spec.spec_trigger (
            {ref},
            event_type text NOT NULL,
            PRIMARY KEY (spec_registry_id, event_type)
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE spec.spec_outcome_route (
            spec_outcome_route_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            {ref},
            outcome_status text NOT NULL
                CHECK (outcome_status IN ('pass', 'rework', 'exception', 'escalate', 'terminate')),
            root_cause text NULL,
            destination_kind text NOT NULL CHECK (destination_kind IN
                ('terminal', 'event', 'special', 'template', 'disabled', 'terminating')),
            destination text NOT NULL,
            alternatives text[] NOT NULL DEFAULT '{{}}',
            requires text[] NOT NULL DEFAULT '{{}}',
            recheck_at text[] NOT NULL DEFAULT '{{}}',
            set_by text[] NOT NULL DEFAULT '{{}}',
            notify text[] NOT NULL DEFAULT '{{}}',
            condition text NULL
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX spec_outcome_route_key ON spec.spec_outcome_route "
        "(spec_registry_id, outcome_status, coalesce(root_cause, ''))"
    )
    op.execute(
        f"""
        CREATE TABLE spec.spec_event_route (
            {ref},
            event_type text NOT NULL,
            destination_kind text NOT NULL,
            destination text NOT NULL,
            immediate text[] NOT NULL DEFAULT '{{}}',
            then_destination text NULL,
            notify text[] NOT NULL DEFAULT '{{}}',
            condition text NULL,
            PRIMARY KEY (spec_registry_id, event_type)
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE spec.spec_change_class (
            {ref},
            change_class text NOT NULL,
            reentry_terminal text NOT NULL,
            path text[] NOT NULL DEFAULT '{{}}',
            retrospective text[] NOT NULL DEFAULT '{{}}',
            within text NULL,
            alternative text NULL,
            PRIMARY KEY (spec_registry_id, change_class)
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE spec.spec_timeline (
            {ref},
            risk_tier text NOT NULL CHECK (risk_tier IN ('low', 'medium', 'high')),
            expected_duration text NULL,
            continuous boolean NOT NULL,
            reminder_after text NOT NULL,
            escalate_after text NULL,
            escalate_at_window_end boolean NOT NULL,
            max_rework_cycles integer NOT NULL,
            clarification_sla text NOT NULL,
            max_clarification_rounds integer NOT NULL,
            max_auto_retries integer NULL,
            retirement_duration text NULL,
            PRIMARY KEY (spec_registry_id, risk_tier)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE spec.usecase_spec_pin (
            usecase_id text NOT NULL CHECK (usecase_id ~ '^UC-[0-9]{4}$'),
            terminal_id text NOT NULL,
            version text NOT NULL,
            pinned_at timestamptz NOT NULL DEFAULT now(),
            pinned_reason text NOT NULL,
            PRIMARY KEY (usecase_id, terminal_id),
            FOREIGN KEY (terminal_id, version) REFERENCES spec.spec_registry (terminal_id, version)
        )
        """
    )
    op.execute(
        """
        CREATE FUNCTION spec.reject_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'spec.% is append-only: % refused', TG_TABLE_NAME, TG_OP
                USING ERRCODE = '42501';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION spec.guard_status_transition() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            old_rest jsonb := to_jsonb(OLD) - 'status' - 'deprecated_at' - 'retired_at';
            new_rest jsonb := to_jsonb(NEW) - 'status' - 'deprecated_at' - 'retired_at';
        BEGIN
            IF old_rest IS DISTINCT FROM new_rest THEN
                RAISE EXCEPTION 'spec.% is immutable: only status may change', TG_TABLE_NAME
                    USING ERRCODE = '42501';
            END IF;
            IF NOT ((OLD.status = 'active' AND NEW.status IN ('deprecated', 'retired'))
                    OR (OLD.status = 'deprecated' AND NEW.status = 'retired')) THEN
                RAISE EXCEPTION 'spec.% status % -> % not allowed',
                    TG_TABLE_NAME, OLD.status, NEW.status
                    USING ERRCODE = '42501';
            END IF;
            IF TG_TABLE_NAME = 'spec_registry' AND NEW.status = 'retired' AND EXISTS (
                SELECT 1 FROM spec.usecase_spec_pin p
                WHERE p.terminal_id = (to_jsonb(OLD) ->> 'terminal_id')
                  AND p.version = (to_jsonb(OLD) ->> 'version')
            ) THEN
                RAISE EXCEPTION
                    'spec.spec_registry % % is pinned by a use case and cannot be retired',
                    to_jsonb(OLD) ->> 'terminal_id', to_jsonb(OLD) ->> 'version'
                    USING ERRCODE = '42501';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    for table in APPEND_ONLY:
        op.execute(
            f"CREATE TRIGGER {table}_no_change BEFORE UPDATE OR DELETE ON spec.{table} "
            "FOR EACH ROW EXECUTE FUNCTION spec.reject_mutation()"
        )
    for table in STATUS_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_status_only BEFORE UPDATE ON spec.{table} "
            "FOR EACH ROW EXECUTE FUNCTION spec.guard_status_transition()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON spec.{table} "
            "FOR EACH ROW EXECUTE FUNCTION spec.reject_mutation()"
        )
    for table in (*STATUS_TABLES, *APPEND_ONLY):
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON spec.{table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION spec.reject_mutation()"
        )
    for table in ALL_TABLES:
        op.execute(f"REVOKE ALL ON spec.{table} FROM PUBLIC")
        op.execute(f"GRANT SELECT ON spec.{table} TO {app}")


def downgrade(**kwargs: Any) -> None:
    for table in reversed(ALL_TABLES):
        op.execute(f"DROP TABLE spec.{table}")
    op.execute("DROP FUNCTION spec.guard_status_transition()")
    op.execute("DROP FUNCTION spec.reject_mutation()")
