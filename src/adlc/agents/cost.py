"""Lifecycle agent cost: alerts and readers (006 FR-021, FR-022; NFR-06).

Each recorded model call is priced by the gateway (catalogue prices). After each call, the use
case's total is compared with the alert levels; the first time a level is reached one
``run.cost_alert`` row is written (the unique key makes it idempotent). Alerts never stop runs.
"""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import Engine, text

TOTALS = ("calls", "tokens_in", "tokens_out", "cost_usd", "unknown_cost_calls", "fallback_answers")


class CostAlerts:
    def __init__(self, engine: Engine, levels: Sequence[Decimal]) -> None:
        self.engine = engine
        self.levels = sorted(levels)

    def check(self, row: Mapping[str, Any]) -> None:
        if not self.levels or row.get("outcome") != "ok":
            return
        usecase = str(row["usecase_id"])
        with self.engine.begin() as conn:
            total = conn.execute(
                text("SELECT cost_usd FROM run.v_usecase_cost WHERE usecase_id = :u"),
                {"u": usecase},
            ).scalar()
            reached = [level for level in self.levels if total is not None and total >= level]
            for level in reached:
                conn.execute(
                    text(
                        "INSERT INTO run.cost_alert (usecase_id, level_usd, total_usd) "
                        "VALUES (:u, :l, :t) ON CONFLICT (usecase_id, level_usd) DO NOTHING"
                    ),
                    {"u": usecase, "l": level, "t": total},
                )


def _one(engine: Engine, sql: str, **params: Any) -> dict[str, Any]:
    with engine.connect() as conn:
        row = conn.execute(text(sql), params).mappings().first()
    if row is None:
        return {k: (Decimal(0) if k == "cost_usd" else 0) for k in TOTALS}
    return {k: row[k] for k in TOTALS}


def run_cost(engine: Engine, run_id: str) -> dict[str, Any]:
    return _one(engine, "SELECT * FROM run.v_run_cost WHERE run_id = :r", r=run_id)


def terminal_cost(engine: Engine, usecase_id: str, terminal_id: str) -> dict[str, Any]:
    return _one(
        engine,
        "SELECT * FROM run.v_terminal_cost WHERE usecase_id = :u AND terminal_id = :t",
        u=usecase_id,
        t=terminal_id,
    )


def usecase_cost(engine: Engine, usecase_id: str) -> dict[str, Any]:
    return _one(engine, "SELECT * FROM run.v_usecase_cost WHERE usecase_id = :u", u=usecase_id)


def alerts(engine: Engine, usecase_id: str) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT level_usd, total_usd, recorded_at FROM run.cost_alert "
                "WHERE usecase_id = :u ORDER BY level_usd"
            ),
            {"u": usecase_id},
        ).mappings()
        return [dict(r) for r in rows]
