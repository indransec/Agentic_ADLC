"""Sync health from the sync tables (FR-022; contracts/api-cli-settings.md "GET /board/health").

Only counts, times and ids: never field values, comments, answers or tokens.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Engine

from adlc.engagement import store


def _age(now: datetime, then: Any) -> float | None:
    if then is None:
        return None
    if isinstance(then, str):
        then = datetime.fromisoformat(then.replace("Z", "+00:00"))
    return max(0.0, float((now - then).total_seconds()))


def health(engine: Engine, *, enabled: bool, now: datetime) -> dict[str, Any]:
    with engine.connect() as conn:
        state = store.sync_state(conn)
        delivery = store.delivery_summary(conn)
        outcomes = store.outcome_counts(conn)
        last = store.reconciliation(conn)
    return {
        "enabled": enabled,
        "mapping_ok": state.last_poll_outcome != "mapping_invalid",
        "last_poll_at": state.last_poll_at,
        "last_poll_outcome": state.last_poll_outcome,
        "watermark": state.watermark,
        "watermark_age_s": _age(now, state.watermark),
        "outbound_pending": delivery["pending"],
        "outbound_oldest_age_s": _age(now, delivery["oldest_dirty_since"]),
        "dead_lettered": delivery["dead_lettered"],
        "refused_by_reason": outcomes["refused_by_reason"],
        "reverted_count": outcomes["reverted"],
        "last_reconciliation": None
        if last is None
        else {"id": last["id"], "at": last["ended_at"], "differences": len(last["differences"])},
    }
