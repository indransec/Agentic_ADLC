"""Decision records (FR-019 to FR-021) and the SQL the policy engine needs.

A decision is written in its own short transaction, so it is kept even when the caller's
transaction rolls back, and never takes the caller's row locks (research R-08).
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import Engine, text

REASON_MAX = 2000


@dataclass(frozen=True)
class PolicyDecision:
    kind: str  # evaluate | authorize
    check_id: str
    rule: str
    passed: bool
    reason: str
    run_id: str | None = None
    usecase_id: str | None = None
    terminal_id: str | None = None
    actor: str | None = None
    value: Any = None
    inputs: Mapping[str, Any] = field(default_factory=dict)
    synthetic: bool = False
    fail_safe: bool = False
    duration_ms: float = 0.0
    attempt: int | None = None  # 005: build attempt of a control check


class DecisionSink(Protocol):
    def record(self, decision: PolicyDecision) -> None: ...


class NullSink:
    def record(self, decision: PolicyDecision) -> None:
        return None


class MemorySink:
    def __init__(self) -> None:
        self.decisions: list[PolicyDecision] = []

    def record(self, decision: PolicyDecision) -> None:
        self.decisions.append(decision)


class SqlDecisionSink:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def record(self, decision: PolicyDecision) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO run.policy_decision (kind, run_id, usecase_id, terminal_id, "
                    "check_id, rule, actor, passed, value, reason, inputs, synthetic, fail_safe, "
                    "duration_ms, attempt) VALUES (:kind, :run_id, :usecase_id, :terminal_id, "
                    ":check_id, :rule, :actor, :passed, CAST(:value AS jsonb), :reason, "
                    "CAST(:inputs AS jsonb), :synthetic, :fail_safe, :duration_ms, :attempt)"
                ),
                {
                    "kind": decision.kind,
                    "run_id": decision.run_id,
                    "usecase_id": decision.usecase_id,
                    "terminal_id": decision.terminal_id,
                    "check_id": decision.check_id,
                    "rule": decision.rule,
                    "actor": decision.actor,
                    "passed": decision.passed,
                    "value": json.dumps(decision.value, default=str),
                    "reason": decision.reason[:REASON_MAX],
                    "inputs": json.dumps(decision.inputs, default=str),
                    "synthetic": decision.synthetic,
                    "fail_safe": decision.fail_safe,
                    "duration_ms": round(decision.duration_ms, 3),
                    "attempt": decision.attempt,
                },
            )


def decisions_for_run(engine: Engine, run_id: str) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT kind, check_id, rule, actor, passed, value, reason, inputs, synthetic, "
                "fail_safe, duration_ms, decided_at FROM run.policy_decision WHERE run_id = :r "
                "ORDER BY decided_at, policy_decision_id"
            ),
            {"r": run_id},
        ).mappings()
        return [dict(r) for r in rows]


# ------------------------------------------------------------------ evidence queries


def latest_closed_run_id(conn: Any, usecase_id: str, terminal_id: str) -> str | None:
    value = conn.execute(
        text(
            "SELECT run_id FROM run.terminal_run WHERE usecase_id = :u AND terminal_id = :t "
            "AND state = 'closed' ORDER BY run_number DESC LIMIT 1"
        ),
        {"u": usecase_id, "t": terminal_id},
    ).scalar()
    return None if value is None else str(value)


def emitted_values(conn: Any, run_id: str) -> dict[str, Any]:
    value = conn.execute(
        text("SELECT content_json -> 'emitted' FROM ledger.ledger_record WHERE run_id = :r"),
        {"r": run_id},
    ).scalar()
    return dict(value) if isinstance(value, dict) else {}


def approved_waivers(conn: Any, usecase_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT w.waiver_id, w.run_id, w.expiry, w.status FROM run.waiver w "
            "JOIN run.terminal_run r USING (run_id) WHERE r.usecase_id = :u "
            "AND w.status = 'approved' ORDER BY w.waiver_id"
        ),
        {"u": usecase_id},
    ).mappings()
    return [dict(r) for r in rows]
