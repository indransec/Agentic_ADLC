"""SQL for the agent runtime's records (006 data-model.md).

Each record is written in its own short transaction, like feature 004's policy decisions, so an
interrupted or rolled-back step keeps the calls it already made (spec edge case "worker crash").
"""

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import Engine, text

MODEL_CALL_COLUMNS = (
    "agent_attempt_ref",
    "run_id",
    "usecase_id",
    "terminal_id",
    "agent_id",
    "tier",
    "entry_index",
    "provider",
    "model",
    "prompt_hash",
    "context_hash",
    "tokens_in",
    "tokens_out",
    "usage_estimated",
    "cost_usd",
    "cost_known",
    "latency_ms",
    "outcome",
    "reason",
    "fallback",
    "called_at",
)
ATTEMPT_COLUMNS = (
    "run_id",
    "kind",
    "attempt",
    "agent_id",
    "agent_version",
    "implementation",
    "prompt_hash",
    "context_hash",
    "steps",
    "tokens_in",
    "tokens_out",
    "cost_usd",
    "corrections",
    "outcome",
    "limit_reached",
    "reason",
    "started_at",
    "ended_at",
)


def _insert(columns: tuple[str, ...], json_columns: tuple[str, ...], table: str) -> str:
    names = ", ".join((*columns, *json_columns))
    values = ", ".join(
        (*(f":{c}" for c in columns), *(f"CAST(:{c} AS jsonb)" for c in json_columns))
    )
    return f"INSERT INTO {table} ({names}) VALUES ({values})"  # noqa: S608 - fixed names


INSERT_CALL = _insert(MODEL_CALL_COLUMNS, ("tried",), "run.model_call")
INSERT_ATTEMPT = _insert(ATTEMPT_COLUMNS, ("playbook_hashes",), "run.agent_attempt")


class SqlCallRecorder:
    """``CallRecorder`` writing ``run.model_call`` rows."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def record(self, row: Mapping[str, Any]) -> None:
        params = {c: row.get(c) for c in MODEL_CALL_COLUMNS}
        params["tried"] = json.dumps(list(row.get("tried") or []))
        with self.engine.begin() as conn:
            conn.execute(text(INSERT_CALL), params)


def insert_attempt(engine: Engine, row: Mapping[str, Any]) -> None:
    params = {c: row.get(c) for c in ATTEMPT_COLUMNS}
    if params["reason"] is not None:
        params["reason"] = str(params["reason"])[:2000]
    params["playbook_hashes"] = json.dumps(dict(row.get("playbook_hashes") or {}))
    with engine.begin() as conn:
        conn.execute(text(INSERT_ATTEMPT), params)


def model_calls(engine: Engine, run_id: str) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM run.model_call WHERE run_id = :r ORDER BY model_call_id"),
            {"r": run_id},
        ).mappings()
        return [dict(r) for r in rows]


def attempts(engine: Engine, run_id: str) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM run.agent_attempt WHERE run_id = :r ORDER BY agent_attempt_id"),
            {"r": run_id},
        ).mappings()
        return [dict(r) for r in rows]
