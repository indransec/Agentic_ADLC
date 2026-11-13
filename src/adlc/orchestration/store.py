"""SQL for the run, events and ledger tables (data-model.md).

Every function takes a connection, so the caller owns the transaction (research R-01). SQL is
written out in full; no statement is built from strings.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, text

from adlc.orchestration.ledger import LedgerRecord
from adlc.orchestration.states import RunState


def _json(value: Any) -> str:
    return json.dumps(value, default=str)


# ------------------------------------------------------------------ use cases and pins


@dataclass(frozen=True)
class UseCaseRow:
    usecase_id: str
    name: str
    intake_text: str
    submitted_by: str
    risk_tier: str | None
    status: str


def next_usecase_number(conn: Connection) -> int:
    return int(conn.execute(text("SELECT nextval('run.usecase_seq')")).scalar_one())


def insert_usecase(
    conn: Connection, usecase_id: str, name: str, intake_text: str, owner: str
) -> None:
    conn.execute(
        text(
            "INSERT INTO run.usecase (usecase_id, name, intake_text, submitted_by) "
            "VALUES (:u, :n, :i, :o)"
        ),
        {"u": usecase_id, "n": name, "i": intake_text, "o": owner},
    )


def load_usecase(conn: Connection, usecase_id: str, *, lock: bool = False) -> UseCaseRow | None:
    sql = (
        "SELECT usecase_id, name, intake_text, submitted_by, risk_tier, status "
        "FROM run.usecase WHERE usecase_id = :u FOR NO KEY UPDATE"
        if lock
        else "SELECT usecase_id, name, intake_text, submitted_by, risk_tier, status "
        "FROM run.usecase WHERE usecase_id = :u"
    )
    row = conn.execute(text(sql), {"u": usecase_id}).mappings().first()
    return None if row is None else UseCaseRow(**row)


def set_usecase_tier(conn: Connection, usecase_id: str, tier: str) -> None:
    conn.execute(
        text("UPDATE run.usecase SET risk_tier = :t WHERE usecase_id = :u"),
        {"t": tier, "u": usecase_id},
    )


def end_usecase(conn: Connection, usecase_id: str, status: str, now: datetime) -> None:
    conn.execute(
        text(
            "UPDATE run.usecase SET status = :s, closed_at = :now "
            "WHERE usecase_id = :u AND status = 'active'"
        ),
        {"s": status, "u": usecase_id, "now": now},
    )


def active_spec_versions(conn: Connection) -> list[tuple[str, str]]:
    rows = conn.execute(
        text(
            "SELECT terminal_id, version FROM spec.spec_registry WHERE status = 'active' "
            "ORDER BY terminal_id"
        )
    )
    return [(str(r[0]), str(r[1])) for r in rows]


def insert_pin(
    conn: Connection, usecase_id: str, terminal_id: str, version: str, reason: str
) -> None:
    conn.execute(
        text(
            "INSERT INTO spec.usecase_spec_pin (usecase_id, terminal_id, version, pinned_reason) "
            "VALUES (:u, :t, :v, :r)"
        ),
        {"u": usecase_id, "t": terminal_id, "v": version, "r": reason},
    )


def pins(conn: Connection, usecase_id: str) -> dict[str, str]:
    rows = conn.execute(
        text("SELECT terminal_id, version FROM spec.usecase_spec_pin WHERE usecase_id = :u"),
        {"u": usecase_id},
    )
    return {str(r[0]): str(r[1]) for r in rows}


# ------------------------------------------------------------------ runs


@dataclass(frozen=True)
class RunRow:
    run_id: str
    usecase_id: str
    terminal_id: str
    run_number: int
    spec_version: str
    state: RunState
    return_state: RunState | None
    mode: str
    trigger_event_id: UUID | None
    trigger_event_type: str
    trigger_context: dict[str, Any]
    rework_count: int
    auto_retries: int
    clarification_rounds: int
    artifacts: dict[str, Any]
    control_results: list[dict[str, Any]]
    recommendation: dict[str, Any] | None
    received_events: list[dict[str, Any]]
    pending_waiver_id: str | None
    escalation_trigger: str | None
    escalation_destination: str | None
    final_status: str | None
    version: int
    lease_until: datetime | None
    opened_at: datetime
    due_at: datetime | None
    closed_at: datetime | None
    profile_version: int = 0  # 005: the profile version current when the run opened
    approvals_after_sign_off_id: int | None = None  # 005: earlier approvals no longer count
    controls_pending: bool = False  # 005: an edit's controls are not re-run yet
    model_unavailable_since: datetime | None = None  # 006: start of a full model outage


def _run(row: Mapping[str, Any] | Any) -> RunRow:
    values = dict(row)
    values["state"] = RunState(values["state"])
    values["return_state"] = (
        None if values["return_state"] is None else RunState(values["return_state"])
    )
    return RunRow(**values)


def load_run(conn: Connection, run_id: str, *, lock: bool = False) -> RunRow | None:
    sql = (
        "SELECT run_id, usecase_id, terminal_id, run_number, spec_version, state, return_state, "
        "mode, trigger_event_id, trigger_event_type, trigger_context, rework_count, auto_retries, "
        "clarification_rounds, artifacts, control_results, recommendation, received_events, "
        "pending_waiver_id, escalation_trigger, escalation_destination, final_status, version, "
        "lease_until, opened_at, due_at, closed_at, profile_version, approvals_after_sign_off_id, "
        "controls_pending, model_unavailable_since "
        "FROM run.terminal_run "
        "WHERE run_id = :r"
    )
    if lock:
        # NO KEY UPDATE: serializes writers of the run, but lets rows that reference it (for
        # example 004's frozen parameter set) be inserted from another connection meanwhile.
        sql += " FOR NO KEY UPDATE"
    row = conn.execute(text(sql), {"r": run_id}).mappings().first()
    return None if row is None else _run(row)


def runs_of_usecase(conn: Connection, usecase_id: str) -> list[RunRow]:
    rows = conn.execute(
        text(
            "SELECT run_id, usecase_id, terminal_id, run_number, spec_version, state, "
            "return_state, mode, trigger_event_id, trigger_event_type, trigger_context, "
            "rework_count, auto_retries, clarification_rounds, artifacts, control_results, "
            "recommendation, received_events, pending_waiver_id, escalation_trigger, "
            "escalation_destination, final_status, version, lease_until, opened_at, due_at, "
            "closed_at, profile_version, approvals_after_sign_off_id, controls_pending, "
            "model_unavailable_since FROM run.terminal_run "
            "WHERE usecase_id = :u "
            "ORDER BY opened_at, run_id"
        ),
        {"u": usecase_id},
    ).mappings()
    return [_run(r) for r in rows]


def active_run(conn: Connection, usecase_id: str, terminal_id: str) -> str | None:
    value = conn.execute(
        text(
            "SELECT run_id FROM run.terminal_run WHERE usecase_id = :u AND terminal_id = :t "
            "AND state <> 'closed'"
        ),
        {"u": usecase_id, "t": terminal_id},
    ).scalar()
    return None if value is None else str(value)


def run_history(conn: Connection, usecase_id: str, terminal_id: str) -> list[tuple[int, str]]:
    rows = conn.execute(
        text(
            "SELECT run_number, trigger_event_type FROM run.terminal_run "
            "WHERE usecase_id = :u AND terminal_id = :t ORDER BY run_number"
        ),
        {"u": usecase_id, "t": terminal_id},
    )
    return [(int(r[0]), str(r[1])) for r in rows]


def latest_closed_artifacts(conn: Connection, usecase_id: str, terminal_id: str) -> dict[str, Any]:
    value = conn.execute(
        text(
            "SELECT artifacts FROM run.terminal_run WHERE usecase_id = :u AND terminal_id = :t "
            "AND state = 'closed' ORDER BY run_number DESC LIMIT 1"
        ),
        {"u": usecase_id, "t": terminal_id},
    ).scalar()
    return dict(value or {})


def insert_run(
    conn: Connection,
    *,
    run_id: str,
    usecase_id: str,
    terminal_id: str,
    run_number: int,
    spec_version: str,
    mode: str,
    trigger_event_id: UUID | None,
    trigger_event_type: str,
    trigger_context: Mapping[str, Any],
    rework_count: int,
    now: datetime,
    due_at: datetime | None,
    profile_version: int = 0,
) -> None:
    conn.execute(
        text(
            "INSERT INTO run.terminal_run (run_id, usecase_id, terminal_id, run_number, "
            "spec_version, state, mode, trigger_event_id, trigger_event_type, trigger_context, "
            "rework_count, opened_at, due_at, profile_version) VALUES (:run_id, :usecase_id, "
            ":terminal_id, :run_number, :spec_version, 'opened', :mode, :trigger_event_id, "
            ":trigger_event_type, CAST(:trigger_context AS jsonb), :rework_count, :now, :due_at, "
            ":profile_version)"
        ),
        {
            "run_id": run_id,
            "usecase_id": usecase_id,
            "terminal_id": terminal_id,
            "run_number": run_number,
            "spec_version": spec_version,
            "mode": mode,
            "trigger_event_id": trigger_event_id,
            "trigger_event_type": trigger_event_type,
            "trigger_context": _json(trigger_context),
            "rework_count": rework_count,
            "now": now,
            "due_at": due_at,
            "profile_version": profile_version,
        },
    )


def save_run(conn: Connection, run: RunRow, now: datetime) -> None:
    """Write the run's mutable fields and bump ``version`` (caller holds the row lock)."""
    conn.execute(
        text(
            "UPDATE run.terminal_run SET state = :state, return_state = :return_state, "
            "auto_retries = :auto_retries, clarification_rounds = :clarification_rounds, "
            "artifacts = CAST(:artifacts AS jsonb), "
            "control_results = CAST(:control_results AS jsonb), "
            "recommendation = CAST(:recommendation AS jsonb), "
            "received_events = CAST(:received_events AS jsonb), "
            "pending_waiver_id = :pending_waiver_id, escalation_trigger = :escalation_trigger, "
            "escalation_destination = :escalation_destination, final_status = :final_status, "
            "version = version + 1, lease_until = NULL, closed_at = :closed_at, "
            "approvals_after_sign_off_id = :approvals_after, controls_pending = :controls_pending, "
            "model_unavailable_since = :unavailable_since "
            "WHERE run_id = :run_id"
        ),
        {
            "run_id": run.run_id,
            "state": run.state.value,
            "return_state": None if run.return_state is None else run.return_state.value,
            "auto_retries": run.auto_retries,
            "clarification_rounds": run.clarification_rounds,
            "artifacts": _json(run.artifacts),
            "control_results": _json(run.control_results),
            "recommendation": None if run.recommendation is None else _json(run.recommendation),
            "received_events": _json(run.received_events),
            "pending_waiver_id": run.pending_waiver_id,
            "escalation_trigger": run.escalation_trigger,
            "escalation_destination": run.escalation_destination,
            "final_status": run.final_status,
            "closed_at": run.closed_at if run.state == RunState.CLOSED else None,
            "approvals_after": run.approvals_after_sign_off_id,
            "unavailable_since": run.model_unavailable_since,
            "controls_pending": run.controls_pending,
        },
    )


def lease_next_automatic(
    conn: Connection, now: datetime, lease_until: datetime
) -> tuple[str, bool] | None:
    """Lease one automatic run; ``True`` when its previous lease had expired (interrupted).

    005: a run waiting for people whose controls must be re-run after an edit is also due; an
    expired lease there just means the re-check is done again (no interrupted step)."""
    row = conn.execute(
        text(
            "SELECT run_id, CASE WHEN state IN ('opened', 'building', 'checking', 'reviewing') "
            "AND model_unavailable_since IS NULL THEN lease_until END FROM run.terminal_run "
            "WHERE (state IN ('opened', 'building', 'checking', 'reviewing') "
            "OR (state IN ('awaiting_sign_off', 'escalated') AND controls_pending)) "
            "AND (lease_until IS NULL OR lease_until < :now) "
            "ORDER BY opened_at, run_id LIMIT 1 FOR NO KEY UPDATE SKIP LOCKED"
        ),
        {"now": now},
    ).first()
    if row is None:
        return None
    conn.execute(
        text("UPDATE run.terminal_run SET lease_until = :l WHERE run_id = :r"),
        {"l": lease_until, "r": row[0]},
    )
    return str(row[0]), row[1] is not None


def defer_for_outage(conn: Connection, run_id: str, since: datetime, lease_until: datetime) -> None:
    """006: hold a run through a model outage; its expired lease is a retry, not an interrupt."""
    conn.execute(
        text(
            "UPDATE run.terminal_run SET model_unavailable_since = :s, lease_until = :l "
            "WHERE run_id = :r"
        ),
        {"s": since, "l": lease_until, "r": run_id},
    )


def deferrals_since(conn: Connection, run_id: str, since: datetime) -> int:
    value = conn.execute(
        text(
            "SELECT count(*) FROM run.run_activity WHERE run_id = :r AND outcome = 'deferred' "
            "AND ended_at >= :s"
        ),
        {"r": run_id, "s": since},
    ).scalar()
    return int(value or 0)


def set_lease(conn: Connection, run_id: str, lease_until: datetime) -> None:
    conn.execute(
        text("UPDATE run.terminal_run SET lease_until = :l WHERE run_id = :r"),
        {"l": lease_until, "r": run_id},
    )


# ------------------------------------------------------------------ history


def insert_transition(
    conn: Connection,
    run_id: str,
    from_state: RunState | None,
    to_state: RunState,
    signal_kind: str,
    actor_type: str,
    actor_id: str,
    reason: str | None,
    now: datetime,
) -> None:
    conn.execute(
        text(
            "INSERT INTO run.run_transition (run_id, from_state, to_state, signal_kind, "
            "actor_type, actor_id, reason, at) VALUES (:r, :f, :t, :k, :at, :ai, :reason, :now)"
        ),
        {
            "r": run_id,
            "f": None if from_state is None else from_state.value,
            "t": to_state.value,
            "k": signal_kind,
            "at": actor_type,
            "ai": actor_id,
            "reason": reason,
            "now": now,
        },
    )


def insert_activity(
    conn: Connection,
    run_id: str,
    step: str,
    actor_type: str,
    actor_id: str,
    started_at: datetime,
    ended_at: datetime,
    outcome: str,
    detail: Mapping[str, Any],
) -> None:
    conn.execute(
        text(
            "INSERT INTO run.run_activity (run_id, step, actor_type, actor_id, started_at, "
            "ended_at, outcome, detail) VALUES (:r, :s, :at, :ai, :st, :en, :o, "
            "CAST(:d AS jsonb))"
        ),
        {
            "r": run_id,
            "s": step,
            "at": actor_type,
            "ai": actor_id,
            "st": started_at,
            "en": ended_at,
            "o": outcome,
            "d": _json(detail),
        },
    )


def insert_sign_off(
    conn: Connection,
    run_id: str,
    role: str,
    person: str,
    decision: str,
    payload: Mapping[str, Any],
    now: datetime,
) -> None:
    conn.execute(
        text(
            "INSERT INTO run.sign_off (run_id, role, person, decision, comment, root_cause, "
            "reason_differs, target_terminal, fields, signed_at) VALUES (:r, :role, :p, :d, :c, "
            ":rc, :rd, :tt, CAST(:f AS jsonb), :now)"
        ),
        {
            "r": run_id,
            "role": role,
            "p": person,
            "d": decision,
            "c": payload.get("comment"),
            "rc": payload.get("root_cause"),
            "rd": payload.get("reason"),
            "tt": payload.get("target_terminal"),
            "f": _json(payload.get("fields") or {}),
            "now": now,
        },
    )


def sign_offs(conn: Connection, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT sign_off_id, role, person, decision, comment, root_cause, reason_differs, "
            "target_terminal, fields, signed_at FROM run.sign_off WHERE run_id = :r "
            "ORDER BY sign_off_id"
        ),
        {"r": run_id},
    ).mappings()
    return [dict(r) for r in rows]


def next_waiver_number(conn: Connection) -> int:
    return int(conn.execute(text("SELECT nextval('run.waiver_seq')")).scalar_one())


def insert_waiver(
    conn: Connection,
    *,
    waiver_id: str,
    run_id: str,
    owner: str | None,
    compensating_control: str | None,
    expiry: str | None,
    recheck_at: Sequence[str],
    requires: Mapping[str, Any],
    proposed_by: str,
    now: datetime,
) -> None:
    conn.execute(
        text(
            "INSERT INTO run.waiver (waiver_id, run_id, waiver_owner, compensating_control, "
            "expiry, recheck_at, requires, status, proposed_by, proposed_at) VALUES (:w, :r, :o, "
            ":c, CAST(:e AS date), :ra, CAST(:req AS jsonb), 'proposed', :p, :now)"
        ),
        {
            "w": waiver_id,
            "r": run_id,
            "o": owner,
            "c": compensating_control,
            "e": expiry,
            "ra": list(recheck_at),
            "req": _json(requires),
            "p": proposed_by,
            "now": now,
        },
    )


def load_waiver(conn: Connection, waiver_id: str) -> dict[str, Any] | None:
    row = (
        conn.execute(
            text(
                "SELECT waiver_id, run_id, waiver_owner, compensating_control, expiry, recheck_at, "
                "requires, status, proposed_by, decided_by, decision_comment FROM run.waiver "
                "WHERE waiver_id = :w"
            ),
            {"w": waiver_id},
        )
        .mappings()
        .first()
    )
    return None if row is None else dict(row)


def decide_waiver(
    conn: Connection, waiver_id: str, approve: bool, person: str, comment: str | None, now: datetime
) -> None:
    conn.execute(
        text(
            "UPDATE run.waiver SET status = :s, decided_by = :p, decision_comment = :c, "
            "decided_at = :now WHERE waiver_id = :w"
        ),
        {
            "s": "approved" if approve else "rejected",
            "p": person,
            "c": comment,
            "now": now,
            "w": waiver_id,
        },
    )


def insert_clarification(
    conn: Connection,
    clarification_id: str,
    run_id: str,
    asked_by: str,
    addressed_role: str,
    questions: Sequence[str],
    looked_in: Sequence[str],
    now: datetime,
) -> None:
    conn.execute(
        text(
            "INSERT INTO run.clarification_round (clarification_id, run_id, asked_by, "
            "addressed_role, questions, looked_in, asked_at) VALUES (:c, :r, :a, :role, "
            "CAST(:q AS jsonb), CAST(:l AS jsonb), :now)"
        ),
        {
            "c": clarification_id,
            "r": run_id,
            "a": asked_by,
            "role": addressed_role,
            "q": _json(list(questions)),
            "l": _json(list(looked_in)),
            "now": now,
        },
    )


def insert_answer(
    conn: Connection, clarification_id: str, person: str, answers: Any, now: datetime
) -> None:
    conn.execute(
        text(
            "INSERT INTO run.clarification_answer (clarification_id, answered_by, answers, "
            "answered_at) VALUES (:c, :p, CAST(:a AS jsonb), :now)"
        ),
        {"c": clarification_id, "p": person, "a": _json(answers), "now": now},
    )


def load_clarification(conn: Connection, clarification_id: str) -> dict[str, Any] | None:
    row = (
        conn.execute(
            text(
                "SELECT c.clarification_id, c.run_id, c.asked_by, c.addressed_role, c.questions, "
                "a.answered_by, a.answers FROM run.clarification_round c "
                "LEFT JOIN run.clarification_answer a USING (clarification_id) "
                "WHERE c.clarification_id = :c"
            ),
            {"c": clarification_id},
        )
        .mappings()
        .first()
    )
    return None if row is None else dict(row)


def clarifications(conn: Connection, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT c.clarification_id, c.asked_by, c.addressed_role, c.questions, c.looked_in, "
            "a.answered_by, a.answers FROM run.clarification_round c "
            "LEFT JOIN run.clarification_answer a USING (clarification_id) "
            "WHERE c.run_id = :r ORDER BY c.asked_at, c.clarification_id"
        ),
        {"r": run_id},
    ).mappings()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ timers


def insert_timer(conn: Connection, run_id: str, kind: str, due_at: datetime) -> None:
    conn.execute(
        text("INSERT INTO run.timer (run_id, kind, due_at) VALUES (:r, :k, :d)"),
        {"r": run_id, "k": kind, "d": due_at},
    )


def cancel_timers(conn: Connection, run_id: str, now: datetime, kind: str | None = None) -> None:
    conn.execute(
        text(
            "UPDATE run.timer SET cancelled_at = :now WHERE run_id = :r "
            "AND fired_at IS NULL AND cancelled_at IS NULL "
            "AND (CAST(:k AS text) IS NULL OR kind = :k)"
        ),
        {"now": now, "r": run_id, "k": kind},
    )


def take_due_timer(conn: Connection, now: datetime) -> tuple[int, str, str] | None:
    row = conn.execute(
        text(
            "SELECT timer_id, run_id, kind FROM run.timer WHERE due_at <= :now "
            "AND fired_at IS NULL AND cancelled_at IS NULL ORDER BY due_at, timer_id "
            "LIMIT 1 FOR UPDATE SKIP LOCKED"
        ),
        {"now": now},
    ).first()
    if row is None:
        return None
    conn.execute(
        text("UPDATE run.timer SET fired_at = :now WHERE timer_id = :t"),
        {"now": now, "t": row[0]},
    )
    return int(row[0]), str(row[1]), str(row[2])


# ------------------------------------------------------------------ outbox


@dataclass(frozen=True)
class EventRow:
    event_id: UUID
    event_type: str
    usecase_id: str | None
    correlation_id: str
    causation_run_id: str | None
    payload: dict[str, Any]
    attempts: int


def insert_event(
    conn: Connection,
    *,
    event_id: UUID,
    event_type: str,
    usecase_id: str | None,
    correlation_id: str,
    causation_run_id: str | None,
    payload: Mapping[str, Any],
    now: datetime,
) -> None:
    conn.execute(
        text(
            "INSERT INTO events.outbox_event (event_id, event_type, usecase_id, correlation_id, "
            "causation_run_id, payload, next_attempt_at) VALUES (:id, :t, :u, :c, :r, "
            "CAST(:p AS jsonb), :now)"
        ),
        {
            "id": event_id,
            "t": event_type,
            "u": usecase_id,
            "c": correlation_id,
            "r": causation_run_id,
            "p": _json(payload),
            "now": now,
        },
    )
    conn.execute(text("SELECT pg_notify('adlc_outbox', :u)"), {"u": usecase_id or ""})


def take_next_event(conn: Connection, now: datetime) -> EventRow | None:
    """Oldest due event of a use case with no older event still pending (FR-028)."""
    row = (
        conn.execute(
            text(
                "SELECT e.event_id, e.event_type, e.usecase_id, e.correlation_id, "
                "e.causation_run_id, e.payload, e.attempts FROM events.outbox_event e "
                "WHERE e.processed_at IS NULL AND e.dead_lettered_at IS NULL "
                "AND e.next_attempt_at <= :now AND NOT EXISTS (SELECT 1 FROM events.outbox_event o "
                "WHERE o.usecase_id IS NOT DISTINCT FROM e.usecase_id AND o.processed_at IS NULL "
                "AND o.dead_lettered_at IS NULL AND (o.created_at, o.event_id) < "
                "(e.created_at, e.event_id)) ORDER BY e.created_at, e.event_id "
                "LIMIT 1 FOR UPDATE OF e SKIP LOCKED"
            ),
            {"now": now},
        )
        .mappings()
        .first()
    )
    return None if row is None else EventRow(**row)


def already_processed(conn: Connection, event_id: UUID) -> bool:
    return (
        conn.execute(
            text("SELECT 1 FROM events.processed_event WHERE event_id = :e"), {"e": event_id}
        ).first()
        is not None
    )


def mark_processed(conn: Connection, event_id: UUID, now: datetime) -> None:
    conn.execute(
        text(
            "INSERT INTO events.processed_event (event_id, processed_at) VALUES (:e, :now) "
            "ON CONFLICT (event_id) DO NOTHING"
        ),
        {"e": event_id, "now": now},
    )
    conn.execute(
        text("UPDATE events.outbox_event SET processed_at = :now WHERE event_id = :e"),
        {"e": event_id, "now": now},
    )


def record_failure(
    conn: Connection,
    event_id: UUID,
    attempts: int,
    error: str,
    next_attempt_at: datetime | None,
    now: datetime,
) -> None:
    conn.execute(
        text(
            "UPDATE events.outbox_event SET attempts = :a, last_error = :err, "
            "next_attempt_at = COALESCE(:next, next_attempt_at), "
            "dead_lettered_at = CASE WHEN CAST(:next AS timestamptz) IS NULL THEN :now END "
            "WHERE event_id = :e"
        ),
        {"a": attempts, "err": error[:2000], "next": next_attempt_at, "now": now, "e": event_id},
    )


def dead_letters(conn: Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT event_id, event_type, usecase_id, causation_run_id, attempts, last_error, "
            "dead_lettered_at, (SELECT count(*) FROM events.dead_letter_action d WHERE "
            "d.event_id = e.event_id) AS requeues FROM events.outbox_event e "
            "WHERE dead_lettered_at IS NOT NULL ORDER BY dead_lettered_at, event_id"
        )
    ).mappings()
    return [dict(r) for r in rows]


def dead_letter(conn: Connection, event_id: UUID) -> dict[str, Any] | None:
    """013: one event (dead-lettered or re-queued before) with its payload and re-queue history."""
    row = (
        conn.execute(
            text(
                "SELECT event_id, event_type, usecase_id, causation_run_id, attempts, last_error, "
                "dead_lettered_at, processed_at, payload FROM events.outbox_event "
                "WHERE event_id = :e"
            ),
            {"e": event_id},
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    history = conn.execute(
        text(
            "SELECT action, actor, at FROM events.dead_letter_action WHERE event_id = :e "
            "ORDER BY dead_letter_action_id"
        ),
        {"e": event_id},
    ).mappings()
    return {**dict(row), "history": [dict(h) for h in history]}


def requeue(conn: Connection, event_id: UUID, actor: str, now: datetime) -> bool:
    updated = conn.execute(
        text(
            "UPDATE events.outbox_event SET attempts = 0, next_attempt_at = :now, "
            "dead_lettered_at = NULL WHERE event_id = :e AND dead_lettered_at IS NOT NULL"
        ),
        {"e": event_id, "now": now},
    ).rowcount
    if updated:
        conn.execute(
            text(
                "INSERT INTO events.dead_letter_action (event_id, action, actor, at) "
                "VALUES (:e, 'requeue', :a, :now)"
            ),
            {"e": event_id, "a": actor, "now": now},
        )
    return bool(updated)


def event_caused_by(conn: Connection, run_id: str) -> tuple[UUID, str] | None:
    row = conn.execute(
        text(
            "SELECT event_id, event_type FROM events.outbox_event WHERE causation_run_id = :r "
            "ORDER BY created_at DESC, event_id DESC LIMIT 1"
        ),
        {"r": run_id},
    ).first()
    return None if row is None else (row[0], str(row[1]))


# ------------------------------------------------------------------ ledger


def latest_ledger_hash(conn: Connection, usecase_id: str) -> str | None:
    value = conn.execute(
        text(
            "SELECT content_hash FROM ledger.ledger_record WHERE usecase_id = :u "
            "ORDER BY ledger_record_id DESC LIMIT 1"
        ),
        {"u": usecase_id},
    ).scalar()
    return None if value is None else str(value)


def insert_ledger_record(conn: Connection, record: LedgerRecord, now: datetime) -> None:
    conn.execute(
        text(
            "INSERT INTO ledger.ledger_record (ledger_key, content_hash, previous_record_hash, "
            "written_at, run_id, usecase_id, content_json) VALUES (:k, :h, :p, :now, :r, :u, "
            "CAST(:c AS jsonb))"
        ),
        {
            "k": record.ledger_key,
            "h": record.content_hash,
            "p": record.previous_record_hash,
            "now": now,
            "r": record.run_id,
            "u": record.usecase_id,
            "c": _json(record.content),
        },
    )


# ------------------------------------------------------------------ heartbeat


def beat(conn: Connection, worker_id: str, now: datetime) -> None:
    conn.execute(
        text(
            "INSERT INTO events.orchestrator_heartbeat (worker_id, beat_at) VALUES (:w, :now) "
            "ON CONFLICT (worker_id) DO UPDATE SET beat_at = EXCLUDED.beat_at"
        ),
        {"w": worker_id, "now": now},
    )


def last_beat(conn: Connection) -> datetime | None:
    value = conn.execute(text("SELECT max(beat_at) FROM events.orchestrator_heartbeat")).scalar()
    return value if isinstance(value, datetime) else None


def max_sign_off_id(conn: Connection, run_id: str) -> int | None:
    value = conn.execute(
        text("SELECT max(sign_off_id) FROM run.sign_off WHERE run_id = :r"), {"r": run_id}
    ).scalar()
    return None if value is None else int(value)
