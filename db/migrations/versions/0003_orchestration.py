"""Lifecycle orchestration: use cases, terminal runs, history, timers, outbox (003 data-model.md).

History tables are append-only for every identity (triggers raise SQLSTATE 42501). Mutable
tables are guarded column by column: a closed run is frozen, an event's content never changes
after it is written, a waiver is decided once, a use case changes only its tier and status.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-10
"""

from typing import Any

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None

STATES = (
    "opened",
    "blocked",
    "building",
    "awaiting_clarification",
    "checking",
    "reviewing",
    "awaiting_sign_off",
    "escalated",
    "closed",
)
ACTORS = ("human", "agent", "reviewer", "orchestrator", "system")
STEPS = (
    "prerequisites",
    "build",
    "controls",
    "review",
    "clarification",
    "sign_off",
    "waiver",
    "escalation",
    "close",
    "route",
    "timer",
)
TRIGGERS = (
    "rework_limit",
    "timer",
    "clarification_limit",
    "clarification_sla",
    "retry_limit",
    "budget",
)
APPEND_ONLY = (
    "run.run_transition",
    "run.run_activity",
    "run.sign_off",
    "run.clarification_round",
    "run.clarification_answer",
    "events.dead_letter_action",
)


def _app(kwargs: dict[str, Any]) -> str:
    role = kwargs.get("app_role")
    if not isinstance(role, str) or not role:
        raise RuntimeError("app_role not supplied by env.py")
    return str(op.get_context().dialect.identifier_preparer.quote(role))


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade(**kwargs: Any) -> None:
    app = _app(kwargs)
    _run_tables()
    _event_tables()
    _ledger_extension()
    _guards()
    _grants(app)


def _run_tables() -> None:
    op.execute("CREATE SEQUENCE run.usecase_seq MINVALUE 1 MAXVALUE 9999")
    op.execute("CREATE SEQUENCE run.waiver_seq MINVALUE 1 MAXVALUE 9999")
    op.execute(
        """
        CREATE TABLE run.usecase (
            usecase_id text PRIMARY KEY CHECK (usecase_id ~ '^UC-[0-9]{4}$'),
            name text NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
            intake_text text NOT NULL,
            submitted_by text NOT NULL,
            risk_tier text NULL CHECK (risk_tier IN ('low', 'medium', 'high')),
            status text NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'terminated', 'closed')),
            created_at timestamptz NOT NULL DEFAULT now(),
            closed_at timestamptz NULL
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE run.terminal_run (
            run_id text PRIMARY KEY CHECK (run_id ~ '^UC-[0-9]{{4}}/[A-Z][0-9]+/run-[0-9]+$'),
            usecase_id text NOT NULL REFERENCES run.usecase (usecase_id),
            terminal_id text NOT NULL CHECK (terminal_id ~ '^[A-Z][0-9]+$'),
            run_number integer NOT NULL CHECK (run_number >= 1),
            spec_version text NOT NULL,
            state text NOT NULL CHECK (state IN ({_in(STATES)})),
            return_state text NULL CHECK (return_state IN ({_in(STATES)})),
            mode text NOT NULL CHECK (mode IN ('evolve', 'retire')),
            trigger_event_id uuid NULL,
            trigger_event_type text NOT NULL,
            trigger_context jsonb NOT NULL DEFAULT '{{}}',
            rework_count integer NOT NULL DEFAULT 0 CHECK (rework_count >= 0),
            auto_retries integer NOT NULL DEFAULT 0 CHECK (auto_retries >= 0),
            clarification_rounds integer NOT NULL DEFAULT 0 CHECK (clarification_rounds >= 0),
            artifacts jsonb NOT NULL DEFAULT '{{}}',
            control_results jsonb NOT NULL DEFAULT '[]',
            recommendation jsonb NULL,
            received_events jsonb NOT NULL DEFAULT '[]',
            pending_waiver_id text NULL,
            escalation_trigger text NULL CHECK (escalation_trigger IN ({_in(TRIGGERS)})),
            escalation_destination text NULL,
            final_status text NULL
                CHECK (final_status IN ('pass', 'rework', 'exception', 'escalate', 'terminate')),
            version integer NOT NULL DEFAULT 0,
            lease_until timestamptz NULL,
            opened_at timestamptz NOT NULL DEFAULT now(),
            due_at timestamptz NULL,
            closed_at timestamptz NULL,
            UNIQUE (usecase_id, terminal_id, run_number),
            CHECK ((state = 'closed') = (final_status IS NOT NULL))
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX terminal_run_one_active ON run.terminal_run (usecase_id, terminal_id) "
        "WHERE state <> 'closed'"
    )
    op.execute(
        "CREATE INDEX terminal_run_automatic ON run.terminal_run (lease_until) "
        "WHERE state IN ('opened', 'building', 'checking', 'reviewing')"
    )
    op.execute(
        f"""
        CREATE TABLE run.run_transition (
            run_transition_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            run_id text NOT NULL REFERENCES run.terminal_run (run_id),
            from_state text NULL CHECK (from_state IN ({_in(STATES)})),
            to_state text NOT NULL CHECK (to_state IN ({_in(STATES)})),
            signal_kind text NOT NULL,
            actor_type text NOT NULL CHECK (actor_type IN ({_in(ACTORS)})),
            actor_id text NOT NULL,
            reason text NULL,
            at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE run.run_activity (
            run_activity_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            run_id text NOT NULL REFERENCES run.terminal_run (run_id),
            step text NOT NULL CHECK (step IN ({_in(STEPS)})),
            actor_type text NOT NULL CHECK (actor_type IN ({_in(ACTORS)})),
            actor_id text NOT NULL,
            started_at timestamptz NOT NULL,
            ended_at timestamptz NOT NULL,
            outcome text NOT NULL,
            detail jsonb NOT NULL DEFAULT '{{}}'
        )
        """
    )
    op.execute(
        """
        CREATE TABLE run.sign_off (
            sign_off_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            run_id text NOT NULL REFERENCES run.terminal_run (run_id),
            role text NOT NULL,
            person text NOT NULL,
            decision text NOT NULL CHECK (decision IN ('pass', 'rework', 'exception', 'terminate')),
            comment text NULL,
            root_cause text NULL,
            reason_differs text NULL,
            target_terminal text NULL,
            fields jsonb NOT NULL DEFAULT '{}',
            signed_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE run.waiver (
            waiver_id text PRIMARY KEY CHECK (waiver_id ~ '^WVR-[0-9]{4}$'),
            run_id text NOT NULL REFERENCES run.terminal_run (run_id),
            waiver_owner text NULL,
            compensating_control text NULL,
            expiry date NULL,
            recheck_at text[] NOT NULL DEFAULT '{}',
            requires jsonb NOT NULL DEFAULT '{}',
            status text NOT NULL CHECK (status IN ('proposed', 'approved', 'rejected', 'expired')),
            proposed_by text NOT NULL,
            decided_by text NULL CHECK (decided_by IS NULL OR decided_by <> proposed_by),
            decision_comment text NULL,
            proposed_at timestamptz NOT NULL DEFAULT now(),
            decided_at timestamptz NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE run.clarification_round (
            clarification_id text PRIMARY KEY
                CHECK (clarification_id ~ '^UC-[0-9]{4}/[A-Z][0-9]+/run-[0-9]+/clar-[0-9]+$'),
            run_id text NOT NULL REFERENCES run.terminal_run (run_id),
            asked_by text NOT NULL CHECK (asked_by IN ('agent', 'reviewer')),
            addressed_role text NOT NULL,
            questions jsonb NOT NULL,
            looked_in jsonb NOT NULL DEFAULT '[]',
            asked_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE run.clarification_answer (
            clarification_id text PRIMARY KEY
                REFERENCES run.clarification_round (clarification_id),
            answered_by text NOT NULL,
            answers jsonb NOT NULL,
            answered_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE run.timer (
            timer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            run_id text NOT NULL REFERENCES run.terminal_run (run_id),
            kind text NOT NULL CHECK (kind IN ('escalate_after', 'clarification_sla', 'review_due')),
            due_at timestamptz NOT NULL,
            fired_at timestamptz NULL,
            cancelled_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX timer_due ON run.timer (due_at) "
        "WHERE fired_at IS NULL AND cancelled_at IS NULL"
    )


def _event_tables() -> None:
    op.execute(
        """
        CREATE TABLE events.outbox_event (
            event_id uuid PRIMARY KEY,
            event_type text NOT NULL,
            usecase_id text NULL REFERENCES run.usecase (usecase_id),
            correlation_id text NOT NULL,
            causation_run_id text NULL,
            payload jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            attempts integer NOT NULL DEFAULT 0,
            next_attempt_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            processed_at timestamptz NULL,
            dead_lettered_at timestamptz NULL,
            last_error text NULL CHECK (length(last_error) <= 2000)
        )
        """
    )
    op.execute(
        "CREATE INDEX outbox_pending ON events.outbox_event (usecase_id, created_at) "
        "WHERE processed_at IS NULL AND dead_lettered_at IS NULL"
    )
    op.execute(
        """
        CREATE TABLE events.processed_event (
            event_id uuid PRIMARY KEY REFERENCES events.outbox_event (event_id),
            processed_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE events.dead_letter_action (
            dead_letter_action_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            event_id uuid NOT NULL REFERENCES events.outbox_event (event_id),
            action text NOT NULL CHECK (action IN ('requeue')),
            actor text NOT NULL,
            at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE events.orchestrator_heartbeat (
            worker_id text PRIMARY KEY,
            beat_at timestamptz NOT NULL
        )
        """
    )


def _ledger_extension() -> None:
    op.execute(
        "ALTER TABLE ledger.ledger_record ADD COLUMN run_id text NULL, "
        "ADD COLUMN usecase_id text NULL, ADD COLUMN content_json jsonb NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX ledger_record_run ON ledger.ledger_record (run_id) "
        "WHERE run_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ledger_record_usecase ON ledger.ledger_record (usecase_id, ledger_record_id)"
    )


def _guards() -> None:
    op.execute(
        """
        CREATE FUNCTION run.reject_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '%.% is append-only: % refused', TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP
                USING ERRCODE = '42501';
        END;
        $$
        """
    )
    for table in APPEND_ONLY:
        name = table.replace(".", "_")
        op.execute(
            f"CREATE TRIGGER {name}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION run.reject_mutation()"
        )
        op.execute(
            f"CREATE TRIGGER {name}_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION run.reject_mutation()"
        )
    op.execute(
        """
        CREATE FUNCTION run.guard_terminal_run() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' OR OLD.state = 'closed' THEN
                RAISE EXCEPTION 'closed run % cannot change', OLD.run_id USING ERRCODE = '42501';
            END IF;
            IF NEW.run_id <> OLD.run_id OR NEW.usecase_id <> OLD.usecase_id
               OR NEW.terminal_id <> OLD.terminal_id OR NEW.run_number <> OLD.run_number
               OR NEW.spec_version <> OLD.spec_version OR NEW.opened_at <> OLD.opened_at THEN
                RAISE EXCEPTION 'run identity of % cannot change', OLD.run_id
                    USING ERRCODE = '42501';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER terminal_run_guard BEFORE UPDATE OR DELETE ON run.terminal_run "
        "FOR EACH ROW EXECUTE FUNCTION run.guard_terminal_run()"
    )
    op.execute(
        """
        CREATE FUNCTION run.guard_usecase() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' OR NEW.usecase_id <> OLD.usecase_id OR NEW.name <> OLD.name
               OR NEW.intake_text <> OLD.intake_text OR NEW.submitted_by <> OLD.submitted_by
               OR NEW.created_at <> OLD.created_at THEN
                RAISE EXCEPTION 'use case %: only risk_tier, status, closed_at may change',
                    OLD.usecase_id USING ERRCODE = '42501';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER usecase_guard BEFORE UPDATE OR DELETE ON run.usecase "
        "FOR EACH ROW EXECUTE FUNCTION run.guard_usecase()"
    )
    op.execute(
        """
        CREATE FUNCTION run.guard_waiver() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' OR OLD.status <> 'proposed'
               OR NEW.waiver_id <> OLD.waiver_id OR NEW.run_id <> OLD.run_id
               OR NEW.waiver_owner IS DISTINCT FROM OLD.waiver_owner
               OR NEW.compensating_control IS DISTINCT FROM OLD.compensating_control
               OR NEW.expiry IS DISTINCT FROM OLD.expiry OR NEW.recheck_at <> OLD.recheck_at
               OR NEW.requires <> OLD.requires OR NEW.proposed_by <> OLD.proposed_by
               OR NEW.proposed_at <> OLD.proposed_at THEN
                RAISE EXCEPTION 'waiver %: only a proposed waiver may be decided, once',
                    OLD.waiver_id USING ERRCODE = '42501';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER waiver_guard BEFORE UPDATE OR DELETE ON run.waiver "
        "FOR EACH ROW EXECUTE FUNCTION run.guard_waiver()"
    )
    op.execute(
        """
        CREATE FUNCTION events.guard_outbox() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' OR NEW.event_id <> OLD.event_id
               OR NEW.event_type <> OLD.event_type
               OR NEW.usecase_id IS DISTINCT FROM OLD.usecase_id
               OR NEW.correlation_id <> OLD.correlation_id
               OR NEW.causation_run_id IS DISTINCT FROM OLD.causation_run_id
               OR NEW.payload <> OLD.payload OR NEW.created_at <> OLD.created_at THEN
                RAISE EXCEPTION 'event % content is immutable', OLD.event_id
                    USING ERRCODE = '42501';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER outbox_event_guard BEFORE UPDATE OR DELETE ON events.outbox_event "
        "FOR EACH ROW EXECUTE FUNCTION events.guard_outbox()"
    )


def _grants(app: str) -> None:
    grants = {
        "run.usecase": "SELECT, INSERT, UPDATE",
        "run.terminal_run": "SELECT, INSERT, UPDATE",
        "run.waiver": "SELECT, INSERT, UPDATE",
        "run.timer": "SELECT, INSERT, UPDATE",
        "events.outbox_event": "SELECT, INSERT, UPDATE",
        "events.orchestrator_heartbeat": "SELECT, INSERT, UPDATE",
        "events.processed_event": "SELECT, INSERT",
        **{table: "SELECT, INSERT" for table in APPEND_ONLY},
    }
    for table, privileges in grants.items():
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        op.execute(f"GRANT {privileges} ON {table} TO {app}")
    for sequence in (
        "run.usecase_seq",
        "run.waiver_seq",
        "run.run_transition_run_transition_id_seq",
        "run.run_activity_run_activity_id_seq",
        "run.sign_off_sign_off_id_seq",
        "run.timer_timer_id_seq",
        "events.dead_letter_action_dead_letter_action_id_seq",
    ):
        op.execute(f"GRANT USAGE ON SEQUENCE {sequence} TO {app}")
    op.execute(f"GRANT INSERT ON spec.usecase_spec_pin TO {app}")


def downgrade(**kwargs: Any) -> None:
    app = _app(kwargs)
    op.execute(f"REVOKE INSERT ON spec.usecase_spec_pin FROM {app}")
    op.execute("DROP INDEX ledger.ledger_record_usecase")
    op.execute("DROP INDEX ledger.ledger_record_run")
    op.execute(
        "ALTER TABLE ledger.ledger_record DROP COLUMN content_json, DROP COLUMN usecase_id, "
        "DROP COLUMN run_id"
    )
    for table in (
        "events.orchestrator_heartbeat",
        "events.dead_letter_action",
        "events.processed_event",
        "events.outbox_event",
        "run.timer",
        "run.clarification_answer",
        "run.clarification_round",
        "run.waiver",
        "run.sign_off",
        "run.run_activity",
        "run.run_transition",
        "run.terminal_run",
        "run.usecase",
    ):
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP SEQUENCE run.waiver_seq")
    op.execute("DROP SEQUENCE run.usecase_seq")
    op.execute("DROP FUNCTION events.guard_outbox()")
    op.execute("DROP FUNCTION run.guard_waiver()")
    op.execute("DROP FUNCTION run.guard_usecase()")
    op.execute("DROP FUNCTION run.guard_terminal_run()")
    op.execute("DROP FUNCTION run.reject_mutation()")
