"""Baseline: the whole platform schema in one SQLite file.

The tables of features 001-013, squashed from the earlier PostgreSQL migrations into one SQLite
revision (SQLite has no schemas, so ``run.terminal_run`` is now ``terminal_run``; every table name
was already unique across the old schemas).

Guarantees kept as triggers, which refuse a change for every connection:

- append-only tables refuse UPDATE and DELETE (ledger, history, evidence, decisions);
- spec registry and catalogue rows change only their status, along active -> deprecated ->
  retired (or active -> retired), and a version pinned by a use case is never retired;
- a closed run is frozen and a run's identity never changes; a use case changes only its tier,
  status and closing time; a waiver is decided once; an event's content never changes.

SQLite has no database identities, so nothing stops a process with write access to the file from
dropping a trigger; the ledger's hash chain (``adlc-ledger verify``) still detects any change.

Types the engine converts (``adlc.db.engine``): ``timestamptz`` (ISO 8601 text, UTC), ``date``,
``jsonb`` (JSON text; also used for the former text arrays), ``boolean``, ``numeric``, ``uuid``.

Revision ID: 0001
Revises:
Create Date: 2026-11-19
"""

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None

HASH = "'^sha256:[0-9a-f]{64}$'"
SEMVER = r"'^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'"
NAME = "'^[a-z][a-z0-9]*(_[a-z0-9]+)*$'"
NOW = "(now())"
STATUS = "status IN ('active', 'deprecated', 'retired')"
TIERS = "('low', 'medium', 'high')"
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
ESCALATION_TRIGGERS = (
    "rework_limit",
    "timer",
    "clarification_limit",
    "clarification_sla",
    "retry_limit",
    "budget",
    "model_unavailable",
    "reviewer_failed",
)
TOOL_OUTCOMES = ("ok", "refused", "failed", "timed_out", "unavailable")
RESULT_KINDS = (
    "ci",
    "harness",
    "redteam",
    "dlp",
    "deploy",
    "traffic",
    "kill_switch",
    "environment",
    "observability",
    "monitoring",
)
SYSTEMS = ("servicenow", "cmdb", "agent_registry", "iam", "grc", "eval_store")
RECORD_KINDS = ("change", "incident", "ci", "agent", "revocation", "report", "note")
AUTOMATIC = "('opened', 'building', 'checking', 'reviewing')"
WAITING = "('awaiting_clarification', 'awaiting_sign_off', 'escalated')"
# Use case and waiver numbers (UC-0001, WVR-0001) run from 1 to 9999.
SEQUENCES = ("usecase_seq", "waiver_seq")

APPEND_ONLY = (
    # 001 ledger
    "ledger_record",
    # 002 spec registry (the status tables have their own guard)
    "playbook_registry",
    "spec_trigger",
    "spec_outcome_route",
    "spec_event_route",
    "spec_change_class",
    "spec_timeline",
    # 003 orchestration history
    "run_transition",
    "run_activity",
    "sign_off",
    "clarification_round",
    "clarification_answer",
    "dead_letter_action",
    # 004 policy
    "policy_decision",
    "run_parameter_set",
    # 005 evidence ledger
    "content_blob",
    "file_object",
    "profile_version",
    "verification_run",
    "artifact_version",
    "artifact_attachment",
    "checklist_result",
    # 006 agent runtime
    "prompt_registry",
    "agent_attempt",
    "model_call",
    "cost_alert",
    # 008 terminal agents
    "knowledge_retrieval",
    "artifact_citation",
    # 010 tools
    "tool_call",
    "tool_result",
    "enterprise_record",
)
VIEWS = (
    "v_run_step",
    "v_usecase_terminal_summary",
    "v_run_cost",
    "v_terminal_cost",
    "v_usecase_cost",
)
TABLES = (  # creation order; dropped in reverse
    "sequence_counter",
    "spec_registry",
    "spec_catalogue",
    "playbook_registry",
    "spec_trigger",
    "spec_outcome_route",
    "spec_event_route",
    "spec_change_class",
    "spec_timeline",
    "usecase_spec_pin",
    "prompt_registry",
    "ledger_record",
    "usecase",
    "terminal_run",
    "run_transition",
    "run_activity",
    "sign_off",
    "waiver",
    "clarification_round",
    "clarification_answer",
    "timer",
    "outbox_event",
    "processed_event",
    "dead_letter_action",
    "orchestrator_heartbeat",
    "policy_decision",
    "run_parameter_set",
    "content_blob",
    "file_object",
    "profile_version",
    "verification_run",
    "artifact_version",
    "artifact_attachment",
    "checklist_result",
    "agent_attempt",
    "model_call",
    "cost_alert",
    "knowledge_retrieval",
    "artifact_citation",
    "tool_call",
    "tool_result",
    "enterprise_record",
)


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _refuse(name: str, event: str, table: str, message: str, when: str | None = None) -> None:
    """A trigger that refuses ``event`` on ``table`` (optionally only ``when`` holds)."""
    condition = f" WHEN {when}" if when else ""
    op.execute(
        f"CREATE TRIGGER {name} BEFORE {event} ON {table}{condition} "
        f"BEGIN SELECT RAISE(ABORT, '{message}'); END"
    )


def _changed(columns: tuple[str, ...]) -> str:
    return " OR ".join(f"NEW.{c} IS NOT OLD.{c}" for c in columns)


def upgrade() -> None:
    _sequences()
    _spec_tables()
    _ledger_tables()
    _run_tables()
    _event_tables()
    _policy_tables()
    _evidence_tables()
    _agent_tables()
    _tool_tables()
    _views()
    _guards()


# ----------------------------------------------------------------------------- 003 sequences


def _sequences() -> None:
    op.execute(
        """
        CREATE TABLE sequence_counter (
            name text PRIMARY KEY,
            value integer NOT NULL CHECK (value >= 0 AND value <= max_value),
            max_value integer NOT NULL
        )
        """
    )
    for name in SEQUENCES:
        op.execute(
            f"INSERT INTO sequence_counter (name, value, max_value) VALUES ('{name}', 0, 9999)"
        )


# ---------------------------------------------------------------------------- 002 spec registry


def _spec_tables() -> None:
    op.execute(
        f"""
        CREATE TABLE spec_registry (
            spec_registry_id INTEGER PRIMARY KEY AUTOINCREMENT,
            terminal_id text NOT NULL CHECK (terminal_id REGEXP '^T[0-9]+$'),
            version text NOT NULL CHECK (version REGEXP {SEMVER}),
            status text NOT NULL CHECK ({STATUS}),
            schema_version text NOT NULL,
            spec_yaml text NOT NULL,
            spec_json jsonb NOT NULL,
            content_hash text NOT NULL CHECK (content_hash REGEXP {HASH}),
            trigger_events jsonb NOT NULL,
            emitted_events jsonb NOT NULL,
            registered_at timestamptz NOT NULL DEFAULT {NOW},
            deprecated_at timestamptz NULL,
            retired_at timestamptz NULL,
            UNIQUE (terminal_id, version)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX spec_registry_one_active ON spec_registry (terminal_id) "
        "WHERE status = 'active'"
    )
    op.execute(
        f"""
        CREATE TABLE spec_catalogue (
            spec_catalogue_id INTEGER PRIMARY KEY AUTOINCREMENT,
            catalogue_name text NOT NULL CHECK (catalogue_name REGEXP '^[a-z][a-z0-9_]*$'),
            version text NOT NULL CHECK (version REGEXP {SEMVER}),
            status text NOT NULL CHECK ({STATUS}),
            content_json jsonb NOT NULL,
            content_hash text NOT NULL CHECK (content_hash REGEXP {HASH}),
            registered_at timestamptz NOT NULL DEFAULT {NOW},
            deprecated_at timestamptz NULL,
            retired_at timestamptz NULL,
            UNIQUE (catalogue_name, version)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX spec_catalogue_one_active ON spec_catalogue (catalogue_name) "
        "WHERE status = 'active'"
    )
    op.execute(
        f"""
        CREATE TABLE playbook_registry (
            playbook_registry_id INTEGER PRIMARY KEY AUTOINCREMENT,
            playbook_id text NOT NULL CHECK (playbook_id REGEXP '^PB-(T[0-9]+|SH)-[0-9]{{2}}$'),
            version text NOT NULL CHECK (version REGEXP {SEMVER}),
            path text NOT NULL,
            content_hash text NOT NULL CHECK (content_hash REGEXP {HASH}),
            registered_at timestamptz NOT NULL DEFAULT {NOW},
            UNIQUE (playbook_id, version)
        )
        """
    )
    ref = "spec_registry_id bigint NOT NULL REFERENCES spec_registry (spec_registry_id)"
    op.execute(
        f"""
        CREATE TABLE spec_trigger (
            {ref},
            event_type text NOT NULL,
            PRIMARY KEY (spec_registry_id, event_type)
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE spec_outcome_route (
            spec_outcome_route_id INTEGER PRIMARY KEY AUTOINCREMENT,
            {ref},
            outcome_status text NOT NULL
                CHECK (outcome_status IN ('pass', 'rework', 'exception', 'escalate', 'terminate')),
            root_cause text NULL,
            destination_kind text NOT NULL CHECK (destination_kind IN
                ('terminal', 'event', 'special', 'template', 'disabled', 'terminating')),
            destination text NOT NULL,
            alternatives jsonb NOT NULL DEFAULT '[]',
            requires jsonb NOT NULL DEFAULT '[]',
            recheck_at jsonb NOT NULL DEFAULT '[]',
            set_by jsonb NOT NULL DEFAULT '[]',
            notify jsonb NOT NULL DEFAULT '[]',
            condition text NULL
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX spec_outcome_route_key ON spec_outcome_route "
        "(spec_registry_id, outcome_status, coalesce(root_cause, ''))"
    )
    op.execute(
        f"""
        CREATE TABLE spec_event_route (
            {ref},
            event_type text NOT NULL,
            destination_kind text NOT NULL,
            destination text NOT NULL,
            immediate jsonb NOT NULL DEFAULT '[]',
            then_destination text NULL,
            notify jsonb NOT NULL DEFAULT '[]',
            condition text NULL,
            PRIMARY KEY (spec_registry_id, event_type)
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE spec_change_class (
            {ref},
            change_class text NOT NULL,
            reentry_terminal text NOT NULL,
            path jsonb NOT NULL DEFAULT '[]',
            retrospective jsonb NOT NULL DEFAULT '[]',
            within text NULL,
            alternative text NULL,
            PRIMARY KEY (spec_registry_id, change_class)
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE spec_timeline (
            {ref},
            risk_tier text NOT NULL CHECK (risk_tier IN {TIERS}),
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
        f"""
        CREATE TABLE usecase_spec_pin (
            usecase_id text NOT NULL CHECK (usecase_id REGEXP '^UC-[0-9]{{4}}$'),
            terminal_id text NOT NULL,
            version text NOT NULL,
            pinned_at timestamptz NOT NULL DEFAULT {NOW},
            pinned_reason text NOT NULL,
            PRIMARY KEY (usecase_id, terminal_id),
            FOREIGN KEY (terminal_id, version) REFERENCES spec_registry (terminal_id, version)
        )
        """
    )
    # 006
    op.execute(
        f"""
        CREATE TABLE prompt_registry (
            prompt_registry_id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_id text NOT NULL CHECK (prompt_id REGEXP '^[a-z][a-z0-9]*(-[a-z0-9]+)*$'),
            version text NOT NULL CHECK (version REGEXP {SEMVER}),
            path text NOT NULL,
            content_hash text NOT NULL CHECK (content_hash REGEXP {HASH}),
            registered_at timestamptz NOT NULL DEFAULT {NOW},
            UNIQUE (prompt_id, version)
        )
        """
    )


# ----------------------------------------------------------------------------------- 001 ledger


def _ledger_tables() -> None:
    op.execute(
        f"""
        CREATE TABLE ledger_record (
            ledger_record_id INTEGER PRIMARY KEY AUTOINCREMENT,
            ledger_key text NOT NULL UNIQUE,
            content_hash text NOT NULL CHECK (content_hash REGEXP {HASH}),
            previous_record_hash text NULL
                CHECK (previous_record_hash IS NULL OR previous_record_hash REGEXP {HASH}),
            written_at timestamptz NOT NULL DEFAULT {NOW},
            run_id text NULL,
            usecase_id text NULL,
            content_json jsonb NULL
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX ledger_record_run ON ledger_record (run_id) WHERE run_id IS NOT NULL"
    )
    op.execute("CREATE INDEX ledger_record_usecase ON ledger_record (usecase_id, ledger_record_id)")


# ------------------------------------------------------------------------- 003 orchestration


def _run_tables() -> None:
    op.execute(
        f"""
        CREATE TABLE usecase (
            usecase_id text PRIMARY KEY CHECK (usecase_id REGEXP '^UC-[0-9]{{4}}$'),
            name text NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
            intake_text text NOT NULL,
            submitted_by text NOT NULL,
            risk_tier text NULL CHECK (risk_tier IN {TIERS}),
            status text NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'terminated', 'closed')),
            created_at timestamptz NOT NULL DEFAULT {NOW},
            closed_at timestamptz NULL
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE terminal_run (
            run_id text PRIMARY KEY
                CHECK (run_id REGEXP '^UC-[0-9]{{4}}/[A-Z][0-9]+/run-[0-9]+$'),
            usecase_id text NOT NULL REFERENCES usecase (usecase_id),
            terminal_id text NOT NULL CHECK (terminal_id REGEXP '^[A-Z][0-9]+$'),
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
            escalation_trigger text NULL
                CHECK (escalation_trigger IN ({_in(ESCALATION_TRIGGERS)})),
            escalation_destination text NULL,
            final_status text NULL
                CHECK (final_status IN ('pass', 'rework', 'exception', 'escalate', 'terminate')),
            version integer NOT NULL DEFAULT 0,
            lease_until timestamptz NULL,
            opened_at timestamptz NOT NULL DEFAULT {NOW},
            due_at timestamptz NULL,
            closed_at timestamptz NULL,
            profile_version integer NOT NULL DEFAULT 0,
            approvals_after_sign_off_id bigint NULL,
            controls_pending boolean NOT NULL DEFAULT FALSE,
            model_unavailable_since timestamptz NULL,
            UNIQUE (usecase_id, terminal_id, run_number),
            CHECK ((state = 'closed') = (final_status IS NOT NULL))
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX terminal_run_one_active ON terminal_run (usecase_id, terminal_id) "
        "WHERE state <> 'closed'"
    )
    op.execute(
        "CREATE INDEX terminal_run_automatic ON terminal_run (lease_until) "
        "WHERE state IN ('opened', 'building', 'checking', 'reviewing')"
    )
    op.execute(
        f"""
        CREATE TABLE run_transition (
            run_transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id text NOT NULL REFERENCES terminal_run (run_id),
            from_state text NULL CHECK (from_state IN ({_in(STATES)})),
            to_state text NOT NULL CHECK (to_state IN ({_in(STATES)})),
            signal_kind text NOT NULL,
            actor_type text NOT NULL CHECK (actor_type IN ({_in(ACTORS)})),
            actor_id text NOT NULL,
            reason text NULL,
            at timestamptz NOT NULL DEFAULT {NOW}
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE run_activity (
            run_activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id text NOT NULL REFERENCES terminal_run (run_id),
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
        f"""
        CREATE TABLE sign_off (
            sign_off_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id text NOT NULL REFERENCES terminal_run (run_id),
            role text NOT NULL,
            person text NOT NULL,
            decision text NOT NULL CHECK (decision IN ('pass', 'rework', 'exception', 'terminate')),
            comment text NULL,
            root_cause text NULL,
            reason_differs text NULL,
            target_terminal text NULL,
            fields jsonb NOT NULL DEFAULT '{{}}',
            signed_at timestamptz NOT NULL DEFAULT {NOW}
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE waiver (
            waiver_id text PRIMARY KEY CHECK (waiver_id REGEXP '^WVR-[0-9]{{4}}$'),
            run_id text NOT NULL REFERENCES terminal_run (run_id),
            waiver_owner text NULL,
            compensating_control text NULL,
            expiry date NULL,
            recheck_at jsonb NOT NULL DEFAULT '[]',
            requires jsonb NOT NULL DEFAULT '{{}}',
            status text NOT NULL CHECK (status IN ('proposed', 'approved', 'rejected', 'expired')),
            proposed_by text NOT NULL,
            decided_by text NULL CHECK (decided_by IS NULL OR decided_by <> proposed_by),
            decision_comment text NULL,
            proposed_at timestamptz NOT NULL DEFAULT {NOW},
            decided_at timestamptz NULL
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE clarification_round (
            clarification_id text PRIMARY KEY CHECK (
                clarification_id REGEXP '^UC-[0-9]{{4}}/[A-Z][0-9]+/run-[0-9]+/clar-[0-9]+$'
            ),
            run_id text NOT NULL REFERENCES terminal_run (run_id),
            asked_by text NOT NULL CHECK (asked_by IN ('agent', 'reviewer')),
            addressed_role text NOT NULL,
            questions jsonb NOT NULL,
            looked_in jsonb NOT NULL DEFAULT '[]',
            asked_at timestamptz NOT NULL DEFAULT {NOW}
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE clarification_answer (
            clarification_id text PRIMARY KEY
                REFERENCES clarification_round (clarification_id),
            answered_by text NOT NULL,
            answers jsonb NOT NULL,
            answered_at timestamptz NOT NULL DEFAULT {NOW}
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE timer (
            timer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id text NOT NULL REFERENCES terminal_run (run_id),
            kind text NOT NULL CHECK (kind IN ('escalate_after', 'clarification_sla', 'review_due')),
            due_at timestamptz NOT NULL,
            fired_at timestamptz NULL,
            cancelled_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT {NOW}
        )
        """
    )
    op.execute(
        "CREATE INDEX timer_due ON timer (due_at) WHERE fired_at IS NULL AND cancelled_at IS NULL"
    )


def _event_tables() -> None:
    op.execute(
        f"""
        CREATE TABLE outbox_event (
            event_id uuid PRIMARY KEY,
            event_type text NOT NULL,
            usecase_id text NULL REFERENCES usecase (usecase_id),
            correlation_id text NOT NULL,
            causation_run_id text NULL,
            payload jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT {NOW},
            attempts integer NOT NULL DEFAULT 0,
            next_attempt_at timestamptz NOT NULL DEFAULT {NOW},
            processed_at timestamptz NULL,
            dead_lettered_at timestamptz NULL,
            last_error text NULL CHECK (length(last_error) <= 2000)
        )
        """
    )
    op.execute(
        "CREATE INDEX outbox_pending ON outbox_event (usecase_id, created_at) "
        "WHERE processed_at IS NULL AND dead_lettered_at IS NULL"
    )
    op.execute(
        f"""
        CREATE TABLE processed_event (
            event_id uuid PRIMARY KEY REFERENCES outbox_event (event_id),
            processed_at timestamptz NOT NULL DEFAULT {NOW}
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE dead_letter_action (
            dead_letter_action_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id uuid NOT NULL REFERENCES outbox_event (event_id),
            action text NOT NULL CHECK (action IN ('requeue')),
            actor text NOT NULL,
            at timestamptz NOT NULL DEFAULT {NOW}
        )
        """
    )
    op.execute(
        """
        CREATE TABLE orchestrator_heartbeat (
            worker_id text PRIMARY KEY,
            beat_at timestamptz NOT NULL
        )
        """
    )


# -------------------------------------------------------------------------------- 004 policy


def _policy_tables() -> None:
    op.execute(
        f"""
        CREATE TABLE policy_decision (
            policy_decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            decided_at timestamptz NOT NULL DEFAULT {NOW},
            attempt integer NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX policy_decision_by_run ON policy_decision "
        "(run_id, decided_at, policy_decision_id)"
    )
    op.execute(
        f"""
        CREATE TABLE run_parameter_set (
            run_id text PRIMARY KEY REFERENCES terminal_run (run_id),
            risk_tier text NOT NULL CHECK (risk_tier IN {TIERS}),
            guardrail_version text NOT NULL,
            parameters jsonb NOT NULL,
            rejected jsonb NOT NULL,
            resolved_at timestamptz NOT NULL DEFAULT {NOW}
        )
        """
    )


# ----------------------------------------------------------------------- 005 evidence ledger


def _evidence_tables() -> None:
    op.execute(
        f"""
        CREATE TABLE content_blob (
            content_hash text PRIMARY KEY CHECK (content_hash REGEXP {HASH}),
            body jsonb NOT NULL,
            size integer NOT NULL CHECK (size >= 0),
            stored_at timestamptz NOT NULL DEFAULT {NOW}
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE file_object (
            content_hash text PRIMARY KEY CHECK (content_hash REGEXP {HASH}),
            size bigint NOT NULL CHECK (size >= 0),
            media_type text NOT NULL,
            stored_at timestamptz NOT NULL DEFAULT {NOW}
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE profile_version (
            usecase_id text NOT NULL REFERENCES usecase (usecase_id),
            version integer NOT NULL CHECK (version >= 1),
            profile_values jsonb NOT NULL,
            source_run_id text NOT NULL REFERENCES terminal_run (run_id),
            created_at timestamptz NOT NULL DEFAULT {NOW},
            PRIMARY KEY (usecase_id, version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE verification_run (
            verification_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        f"""
        CREATE TABLE artifact_version (
            run_id text NOT NULL REFERENCES terminal_run (run_id),
            artifact_id text NOT NULL,
            version integer NOT NULL CHECK (version >= 1),
            content_hash text NOT NULL REFERENCES content_blob (content_hash),
            producer_type text NOT NULL CHECK (producer_type IN ('agent', 'person')),
            producer_id text NOT NULL,
            attempt integer NULL,
            derived_from_version integer NULL,
            schema_valid boolean NOT NULL,
            created_at timestamptz NOT NULL DEFAULT {NOW},
            PRIMARY KEY (run_id, artifact_id, version)
        )
        """
    )
    op.execute(
        r"""
        CREATE TABLE artifact_attachment (
            run_id text NOT NULL,
            artifact_id text NOT NULL,
            version integer NOT NULL,
            content_hash text NOT NULL REFERENCES file_object (content_hash),
            file_name text NOT NULL CHECK (length(file_name) BETWEEN 1 AND 255
                AND NOT (file_name REGEXP '[/\\]')),
            media_type text NOT NULL,
            size bigint NOT NULL,
            PRIMARY KEY (run_id, artifact_id, version, content_hash),
            FOREIGN KEY (run_id, artifact_id, version)
                REFERENCES artifact_version (run_id, artifact_id, version)
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE checklist_result (
            checklist_result_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id text NOT NULL REFERENCES terminal_run (run_id),
            attempt integer NOT NULL,
            item_id text NOT NULL,
            score integer NULL,
            finding text NULL,
            recorded_at timestamptz NOT NULL DEFAULT {NOW}
        )
        """
    )


# ------------------------------------------------------------------------- 006 agent runtime


def _agent_tables() -> None:
    op.execute(
        f"""
        CREATE TABLE agent_attempt (
            agent_attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id text NOT NULL REFERENCES terminal_run (run_id),
            kind text NOT NULL CHECK (kind IN ('build', 'review')),
            attempt integer NOT NULL CHECK (attempt >= 1),
            agent_id text NOT NULL,
            agent_version text NOT NULL,
            implementation text NOT NULL CHECK (implementation IN ('stub', 'model')),
            prompt_hash text NULL CHECK (prompt_hash IS NULL OR prompt_hash REGEXP {HASH}),
            playbook_hashes jsonb NOT NULL DEFAULT '{{}}',
            context_hash text NOT NULL CHECK (context_hash REGEXP {HASH}),
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
    op.execute("CREATE INDEX agent_attempt_by_run ON agent_attempt (run_id, agent_attempt_id)")
    op.execute(
        f"""
        CREATE TABLE model_call (
            model_call_id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_attempt_ref text NOT NULL,
            run_id text NOT NULL REFERENCES terminal_run (run_id),
            usecase_id text NOT NULL,
            terminal_id text NOT NULL,
            agent_id text NOT NULL,
            tier text NOT NULL,
            entry_index integer NOT NULL CHECK (entry_index >= 1),
            provider text NOT NULL,
            model text NOT NULL,
            prompt_hash text NULL CHECK (prompt_hash IS NULL OR prompt_hash REGEXP {HASH}),
            context_hash text NOT NULL CHECK (context_hash REGEXP {HASH}),
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
    op.execute("CREATE INDEX model_call_by_run ON model_call (run_id, model_call_id)")
    op.execute("CREATE INDEX model_call_by_usecase ON model_call (usecase_id)")
    op.execute(
        f"""
        CREATE TABLE cost_alert (
            cost_alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
            usecase_id text NOT NULL,
            level_usd numeric(14, 2) NOT NULL CHECK (level_usd > 0),
            total_usd numeric(14, 6) NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT {NOW},
            UNIQUE (usecase_id, level_usd)
        )
        """
    )
    # 008 terminal agents
    op.execute(
        f"""
        CREATE TABLE knowledge_retrieval (
            knowledge_retrieval_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id text NOT NULL REFERENCES terminal_run (run_id),
            attempt integer NOT NULL CHECK (attempt >= 1),
            step integer NOT NULL CHECK (step >= 0),
            source text NOT NULL CHECK (source REGEXP {NAME}),
            operation text NOT NULL CHECK (operation IN ('search', 'read')),
            request text NOT NULL CHECK (length(request) <= 500),
            document text NOT NULL CHECK (length(document) BETWEEN 1 AND 500),
            section text NOT NULL DEFAULT '' CHECK (length(section) <= 500),
            content_hash text NOT NULL CHECK (content_hash REGEXP {HASH}),
            data_class text NOT NULL,
            synthetic boolean NOT NULL,
            retrieved_at timestamptz NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX knowledge_retrieval_by_attempt ON knowledge_retrieval (run_id, attempt)"
    )
    op.execute(
        f"""
        CREATE TABLE artifact_citation (
            artifact_citation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id text NOT NULL,
            artifact_id text NOT NULL,
            version integer NOT NULL,
            row_index integer NULL CHECK (row_index IS NULL OR row_index >= 0),
            source text NOT NULL CHECK (source REGEXP {NAME}),
            document text NOT NULL,
            section text NOT NULL DEFAULT '',
            content_hash text NOT NULL CHECK (content_hash REGEXP {HASH}),
            knowledge_retrieval_id bigint NOT NULL
                REFERENCES knowledge_retrieval (knowledge_retrieval_id),
            cited_at timestamptz NOT NULL,
            FOREIGN KEY (run_id, artifact_id, version)
                REFERENCES artifact_version (run_id, artifact_id, version)
        )
        """
    )
    op.execute(
        "CREATE INDEX artifact_citation_by_version ON artifact_citation "
        "(run_id, artifact_id, version)"
    )


# --------------------------------------------------------------------------------- 010 tools


def _tool_tables() -> None:
    op.execute(
        f"""
        CREATE TABLE tool_call (
            tool_call_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id text NOT NULL,
            usecase_id text NOT NULL,
            terminal_id text NOT NULL,
            attempt integer NOT NULL CHECK (attempt >= 1),
            step integer NOT NULL CHECK (step >= 0),
            tool text NOT NULL CHECK (tool REGEXP {NAME}),
            server text NOT NULL CHECK (server REGEXP {NAME}),
            scope text NOT NULL CHECK (scope REGEXP {NAME}),
            arguments_sha256 text NOT NULL CHECK (arguments_sha256 REGEXP {HASH}),
            outcome text NOT NULL CHECK (outcome IN ({_in(TOOL_OUTCOMES)})),
            reason text NOT NULL DEFAULT '' CHECK (length(reason) <= 2000),
            duration_ms integer NOT NULL CHECK (duration_ms >= 0),
            at timestamptz NOT NULL,
            CHECK (outcome = 'ok' OR reason <> '')
        )
        """
    )
    op.execute("CREATE INDEX tool_call_by_run ON tool_call (run_id, attempt)")
    op.execute(
        f"""
        CREATE TABLE tool_result (
            tool_result_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_call_id bigint NOT NULL REFERENCES tool_call (tool_call_id),
            run_id text NOT NULL,
            usecase_id text NOT NULL,
            terminal_id text NOT NULL,
            kind text NOT NULL CHECK (kind IN ({_in(RESULT_KINDS)})),
            package_hash text NULL CHECK (package_hash IS NULL OR package_hash REGEXP {HASH}),
            result jsonb NOT NULL,
            result_sha256 text NOT NULL CHECK (result_sha256 REGEXP {HASH}),
            at timestamptz NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX tool_result_by_usecase ON tool_result (usecase_id, kind)")
    op.execute(
        f"""
        CREATE TABLE enterprise_record (
            enterprise_record_id INTEGER PRIMARY KEY AUTOINCREMENT,
            system text NOT NULL CHECK (system IN ({_in(SYSTEMS)})),
            kind text NOT NULL CHECK (kind IN ({_in(RECORD_KINDS)})),
            record_id text NOT NULL CHECK (record_id REGEXP '^[A-Z]+-[0-9]+$'),
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
        "CREATE INDEX enterprise_record_by_usecase ON enterprise_record (usecase_id, system)"
    )


# ------------------------------------------------------------------------------------- views


def _seconds(later: str, earlier: str) -> str:
    """Seconds between two stored times (millisecond precision)."""
    return f"(unixepoch({later}, 'subsec') - unixepoch({earlier}, 'subsec'))"


COST_TOTALS = """
    count(*) FILTER (WHERE outcome = 'ok') AS calls,
    COALESCE(SUM(tokens_in), 0) AS tokens_in,
    COALESCE(SUM(tokens_out), 0) AS tokens_out,
    COALESCE(SUM(cost_usd) FILTER (WHERE cost_known), 0) AS cost_usd,
    count(*) FILTER (WHERE NOT cost_known AND outcome = 'ok') AS unknown_cost_calls,
    count(*) FILTER (WHERE fallback AND outcome = 'ok') AS fallback_answers
"""


def _views() -> None:
    op.execute(
        f"""
        CREATE VIEW v_run_step AS
        SELECT run_id, step, actor_type, actor_id, started_at, ended_at,
               {_seconds("ended_at", "started_at")} AS duration_seconds, outcome,
               run_activity_id
        FROM run_activity
        """
    )
    later = (
        "COALESCE(LEAD(t.at) OVER (PARTITION BY t.run_id ORDER BY t.at, t.run_transition_id), "
        "CASE WHEN t.to_state = 'closed' THEN t.at ELSE now() END)"
    )
    op.execute(
        f"""
        CREATE VIEW v_usecase_terminal_summary AS
        WITH spans AS (
            SELECT t.run_id, t.to_state, {_seconds(later, "t.at")} AS spent
            FROM run_transition t
        ),
        per_run AS (
            SELECT r.usecase_id, r.terminal_id, r.run_id, r.rework_count, r.clarification_rounds,
                   r.escalation_trigger,
                   COALESCE(SUM(s.spent) FILTER (WHERE s.to_state IN {AUTOMATIC}), 0)
                       AS automatic_seconds,
                   COALESCE(SUM(s.spent) FILTER (WHERE s.to_state IN {WAITING}), 0)
                       AS waiting_seconds
            FROM terminal_run r LEFT JOIN spans s USING (run_id)
            GROUP BY r.usecase_id, r.terminal_id, r.run_id, r.rework_count,
                     r.clarification_rounds, r.escalation_trigger
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
    op.execute(
        f"CREATE VIEW v_run_cost AS SELECT run_id, usecase_id, terminal_id, {COST_TOTALS} "
        "FROM model_call GROUP BY run_id, usecase_id, terminal_id"
    )
    op.execute(
        f"CREATE VIEW v_terminal_cost AS SELECT usecase_id, terminal_id, {COST_TOTALS} "
        "FROM model_call GROUP BY usecase_id, terminal_id"
    )
    op.execute(
        f"CREATE VIEW v_usecase_cost AS SELECT usecase_id, {COST_TOTALS} "
        "FROM model_call GROUP BY usecase_id"
    )


# ------------------------------------------------------------------------------------ guards


def _guards() -> None:
    for table in APPEND_ONLY:
        for event in ("UPDATE", "DELETE"):
            _refuse(
                f"{table}_no_{event.lower()}",
                event,
                table,
                f"{table} is append-only: {event} refused",
            )
    _status_guards()
    _run_guards()


def _status_guards() -> None:
    """002: registry and catalogue rows change only their status, forward, unless pinned."""
    columns = {
        "spec_registry": (
            "spec_registry_id",
            "terminal_id",
            "version",
            "schema_version",
            "spec_yaml",
            "spec_json",
            "content_hash",
            "trigger_events",
            "emitted_events",
            "registered_at",
        ),
        "spec_catalogue": (
            "spec_catalogue_id",
            "catalogue_name",
            "version",
            "content_json",
            "content_hash",
            "registered_at",
        ),
    }
    forward = (
        "(OLD.status = 'active' AND NEW.status IN ('deprecated', 'retired')) "
        "OR (OLD.status = 'deprecated' AND NEW.status = 'retired')"
    )
    for table, fixed in columns.items():
        _refuse(f"{table}_no_delete", "DELETE", table, f"{table} is append-only: DELETE refused")
        _refuse(
            f"{table}_status_only",
            "UPDATE",
            table,
            f"{table} is immutable: only status may change",
            _changed(fixed),
        )
        _refuse(
            f"{table}_status_forward",
            "UPDATE",
            table,
            f"{table} status change not allowed",
            f"NOT ({forward})",
        )
    _refuse(
        "spec_registry_pinned",
        "UPDATE",
        "spec_registry",
        "spec_registry version is pinned by a use case and cannot be retired",
        "NEW.status = 'retired' AND EXISTS (SELECT 1 FROM usecase_spec_pin p "
        "WHERE p.terminal_id = OLD.terminal_id AND p.version = OLD.version)",
    )


def _run_guards() -> None:
    """003: a closed run is frozen; identities, decided waivers and event content never change."""
    _refuse("terminal_run_no_delete", "DELETE", "terminal_run", "a run cannot be deleted")
    _refuse(
        "terminal_run_closed",
        "UPDATE",
        "terminal_run",
        "a closed run cannot change",
        "OLD.state = 'closed'",
    )
    _refuse(
        "terminal_run_identity",
        "UPDATE",
        "terminal_run",
        "a run identity cannot change",
        _changed(
            ("run_id", "usecase_id", "terminal_id", "run_number", "spec_version", "opened_at")
        ),
    )
    usecase_message = "use case: only risk_tier, status, closed_at may change"
    _refuse("usecase_no_delete", "DELETE", "usecase", usecase_message)
    _refuse(
        "usecase_fixed",
        "UPDATE",
        "usecase",
        usecase_message,
        _changed(("usecase_id", "name", "intake_text", "submitted_by", "created_at")),
    )
    waiver_message = "waiver: only a proposed waiver may be decided, once"
    _refuse("waiver_no_delete", "DELETE", "waiver", waiver_message)
    fixed = (
        "waiver_id",
        "run_id",
        "waiver_owner",
        "compensating_control",
        "expiry",
        "recheck_at",
        "requires",
        "proposed_by",
        "proposed_at",
    )
    _refuse(
        "waiver_decided_once",
        "UPDATE",
        "waiver",
        waiver_message,
        f"OLD.status <> 'proposed' OR {_changed(fixed)}",
    )
    event_message = "event content is immutable"
    _refuse("outbox_event_no_delete", "DELETE", "outbox_event", event_message)
    _refuse(
        "outbox_event_content",
        "UPDATE",
        "outbox_event",
        event_message,
        _changed(
            (
                "event_id",
                "event_type",
                "usecase_id",
                "correlation_id",
                "causation_run_id",
                "payload",
                "created_at",
            )
        ),
    )


def downgrade() -> None:
    for view in reversed(VIEWS):
        op.execute(f"DROP VIEW {view}")
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE {table}")
