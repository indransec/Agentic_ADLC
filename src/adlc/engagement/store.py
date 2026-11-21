"""All SQL of the board tables (data-model.md); every function takes the caller's connection.

The projector's change cursor is three high-water marks over rows that only ever grow in commit
order (SQLite has one writer at a time): ``run_transition`` and ``run_activity`` ids (append-only;
every run change, clarification and decision writes one) and the ``usecase`` rowid (a new use case
before its first run). No timestamps, so clocks of different processes do not matter.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Connection, text

CURSOR_KEYS = ("run_transition_id", "run_activity_id", "usecase_rowid")


@dataclass(frozen=True)
class Link:
    object_kind: str
    object_id: str
    work_item_id: int
    item_type: str
    projected_hash: str | None
    last_written_rev: int | None
    inbound_update_id: int


@dataclass(frozen=True)
class SyncState:
    watermark: str | None
    last_poll_at: datetime | None
    last_poll_outcome: str | None
    last_error: str | None
    cursor: dict[str, int]


@dataclass(frozen=True)
class Claim:
    work_item_id: int
    update_id: int
    rev: int
    changer: str
    account_name: str | None
    kind: str
    object_id: str | None


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


# ------------------------------------------------------------------------------- links

_LINK = (
    "SELECT object_kind, object_id, work_item_id, item_type, projected_hash, last_written_rev, "
    "inbound_update_id FROM board_link"
)


def _link(row: Any) -> Link:
    return Link(
        str(row[0]),
        str(row[1]),
        int(row[2]),
        str(row[3]),
        row[4],
        None if row[5] is None else int(row[5]),
        int(row[6]),
    )


def get_link(conn: Connection, kind: str, object_id: str) -> Link | None:
    row = conn.execute(
        text(f"{_LINK} WHERE object_kind = :k AND object_id = :o"), {"k": kind, "o": object_id}
    ).first()
    return None if row is None else _link(row)


def link_by_item(conn: Connection, work_item_id: int) -> Link | None:
    row = conn.execute(text(f"{_LINK} WHERE work_item_id = :i"), {"i": work_item_id}).first()
    return None if row is None else _link(row)


def links(conn: Connection) -> list[Link]:
    return [_link(r) for r in conn.execute(text(f"{_LINK} ORDER BY object_kind, object_id"))]


def put_link(
    conn: Connection,
    kind: str,
    object_id: str,
    work_item_id: int,
    item_type: str,
    now: datetime,
    *,
    projected_hash: str | None = None,
    rev: int | None = None,
) -> None:
    conn.execute(
        text(
            "INSERT INTO board_link (object_kind, object_id, work_item_id, item_type, "
            "projected_hash, last_written_rev, created_at, updated_at) "
            "VALUES (:k, :o, :i, :t, :h, :r, :n, :n)"
        ),
        {
            "k": kind,
            "o": object_id,
            "i": work_item_id,
            "t": item_type,
            "h": projected_hash,
            "r": rev,
            "n": now,
        },
    )


def delete_link(conn: Connection, kind: str, object_id: str) -> None:
    """Forget a link whose work item is gone from the board (reconciliation creates it again)."""
    conn.execute(
        text("DELETE FROM board_link WHERE object_kind = :k AND object_id = :o"),
        {"k": kind, "o": object_id},
    )


def set_projection(
    conn: Connection, kind: str, object_id: str, projected_hash: str, rev: int, now: datetime
) -> None:
    conn.execute(
        text(
            "UPDATE board_link SET projected_hash = :h, last_written_rev = :r, updated_at = :n "
            "WHERE object_kind = :k AND object_id = :o"
        ),
        {"h": projected_hash, "r": rev, "n": now, "k": kind, "o": object_id},
    )


def set_inbound_update(conn: Connection, work_item_id: int, update_id: int, now: datetime) -> None:
    """Record that inbound sync has processed the item's updates up to ``update_id``."""
    conn.execute(
        text(
            "UPDATE board_link SET inbound_update_id = max(inbound_update_id, :u), "
            "updated_at = :n WHERE work_item_id = :i"
        ),
        {"u": update_id, "n": now, "i": work_item_id},
    )


# ------------------------------------------------------------------------------- sync state


def sync_state(conn: Connection) -> SyncState:
    row = conn.execute(
        text(
            "SELECT watermark, last_poll_at, last_poll_outcome, last_error, projection_cursor "
            "FROM board_sync_state WHERE id = 1"
        )
    ).one()
    cursor = _json(row[4]) or {}
    return SyncState(
        row[0], row[1], row[2], row[3], {k: int(cursor.get(k, 0)) for k in CURSOR_KEYS}
    )


def set_watermark(conn: Connection, watermark: str) -> None:
    conn.execute(text("UPDATE board_sync_state SET watermark = :w WHERE id = 1"), {"w": watermark})


def record_poll(conn: Connection, outcome: str, error: str | None, now: datetime) -> None:
    conn.execute(
        text(
            "UPDATE board_sync_state SET last_poll_at = :n, last_poll_outcome = :o, "
            "last_error = :e WHERE id = 1"
        ),
        {"n": now, "o": outcome, "e": None if error is None else error[:2000]},
    )


def set_cursor(conn: Connection, cursor: dict[str, int]) -> None:
    conn.execute(
        text("UPDATE board_sync_state SET projection_cursor = :c WHERE id = 1"),
        {"c": json.dumps({k: int(cursor.get(k, 0)) for k in CURSOR_KEYS})},
    )


def changed_usecases(conn: Connection, cursor: dict[str, int]) -> tuple[set[str], dict[str, int]]:
    """Use cases with history after ``cursor``, and the cursor moved past it."""
    found: set[str] = set()
    moved = dict(cursor)
    for key, sql in (
        (
            "run_transition_id",
            "SELECT t.run_transition_id, r.usecase_id FROM run_transition t "
            "JOIN terminal_run r ON r.run_id = t.run_id WHERE t.run_transition_id > :c",
        ),
        (
            "run_activity_id",
            "SELECT a.run_activity_id, r.usecase_id FROM run_activity a "
            "JOIN terminal_run r ON r.run_id = a.run_id WHERE a.run_activity_id > :c",
        ),
        ("usecase_rowid", "SELECT rowid, usecase_id FROM usecase WHERE rowid > :c"),
    ):
        for mark, usecase in conn.execute(text(sql), {"c": cursor.get(key, 0)}):
            found.add(str(usecase))
            moved[key] = max(moved.get(key, 0), int(mark))
    return found, moved


def all_usecases(conn: Connection) -> list[str]:
    return [str(r[0]) for r in conn.execute(text("SELECT usecase_id FROM usecase ORDER BY rowid"))]


# ------------------------------------------------------------------------------- delivery


def mark_dirty(conn: Connection, usecases: Iterable[str], now: datetime) -> None:
    """A dead-lettered use case stays dead until requeued (as the outbox)."""
    for usecase in usecases:
        conn.execute(
            text(
                "INSERT INTO board_delivery (usecase_id, dirty_since, next_attempt_at) "
                "VALUES (:u, :n, :n) ON CONFLICT (usecase_id) DO UPDATE SET "
                "dirty_since = coalesce(board_delivery.dirty_since, :n), "
                "next_attempt_at = coalesce(board_delivery.next_attempt_at, :n)"
            ),
            {"u": usecase, "n": now},
        )


def due_deliveries(conn: Connection, now: datetime) -> list[str]:
    return [
        str(r[0])
        for r in conn.execute(
            text(
                "SELECT usecase_id FROM board_delivery WHERE dirty_since IS NOT NULL "
                "AND dead_lettered_at IS NULL AND next_attempt_at <= :n "
                "ORDER BY dirty_since, usecase_id"
            ),
            {"n": now},
        )
    ]


def delivered(conn: Connection, usecase: str, now: datetime) -> None:
    conn.execute(
        text(
            "UPDATE board_delivery SET dirty_since = NULL, attempts = 0, next_attempt_at = NULL, "
            "last_error = NULL, delivered_at = :n WHERE usecase_id = :u"
        ),
        {"n": now, "u": usecase},
    )


def delivery_failed(
    conn: Connection,
    usecase: str,
    error: str,
    now: datetime,
    delays: Sequence[timedelta],
    time_scale: float = 1.0,
) -> bool:
    """Schedule the next try on the outbox's delays; returns True when dead-lettered."""
    attempts = (
        int(
            conn.execute(
                text("SELECT attempts FROM board_delivery WHERE usecase_id = :u"), {"u": usecase}
            ).scalar_one()
        )
        + 1
    )
    dead = attempts > len(delays)
    conn.execute(
        text(
            "UPDATE board_delivery SET attempts = :a, last_error = :e, next_attempt_at = :next, "
            "dead_lettered_at = :dead WHERE usecase_id = :u"
        ),
        {
            "a": attempts,
            "e": error[:2000],
            "next": None if dead else now + delays[attempts - 1] * time_scale,
            "dead": now if dead else None,
            "u": usecase,
        },
    )
    return dead


def requeue(conn: Connection, usecase: str, actor: str, now: datetime) -> bool:
    """Requeue a dead-lettered use case; False when it is not dead-lettered."""
    changed = conn.execute(
        text(
            "UPDATE board_delivery SET dead_lettered_at = NULL, attempts = 0, "
            "next_attempt_at = :n, dirty_since = coalesce(dirty_since, :n) "
            "WHERE usecase_id = :u AND dead_lettered_at IS NOT NULL"
        ),
        {"n": now, "u": usecase},
    ).rowcount
    if not changed:
        return False
    conn.execute(
        text("INSERT INTO board_requeue (usecase_id, actor, at) VALUES (:u, :a, :n)"),
        {"u": usecase, "a": actor, "n": now},
    )
    return True


def delivery_summary(conn: Connection) -> dict[str, Any]:
    pending, oldest = conn.execute(
        text(
            "SELECT count(*), min(dirty_since) FROM board_delivery "
            "WHERE dirty_since IS NOT NULL AND dead_lettered_at IS NULL"
        )
    ).one()
    dead = [
        str(r[0])
        for r in conn.execute(
            text(
                "SELECT usecase_id FROM board_delivery WHERE dead_lettered_at IS NOT NULL "
                "ORDER BY usecase_id"
            )
        )
    ]
    return {"pending": int(pending), "oldest_dirty_since": oldest, "dead_lettered": dead}


# ------------------------------------------------------------------------------- inbound


def claim(conn: Connection, change: Claim, now: datetime) -> bool:
    """Record a board update before acting on it; False when it was already recorded."""
    return bool(
        conn.execute(
            text(
                "INSERT INTO inbound_change (work_item_id, update_id, rev, changer, "
                "account_name, kind, object_id, read_at) VALUES (:i, :u, :r, :c, :a, :k, :o, :n) "
                "ON CONFLICT (work_item_id, update_id) DO NOTHING"
            ),
            {
                "i": change.work_item_id,
                "u": change.update_id,
                "r": change.rev,
                "c": change.changer,
                "a": change.account_name,
                "k": change.kind,
                "o": change.object_id,
                "n": now,
            },
        ).rowcount
    )


def max_update_id(conn: Connection, work_item_id: int) -> int:
    """The highest update of an item inbound sync has read (claimed), linked or not."""
    value = conn.execute(
        text("SELECT max(update_id) FROM inbound_change WHERE work_item_id = :i"),
        {"i": work_item_id},
    ).scalar_one()
    return 0 if value is None else int(value)


def write_outcome(
    conn: Connection,
    work_item_id: int,
    update_id: int,
    outcome: str,
    now: datetime,
    *,
    reason_code: str | None = None,
    reason: str | None = None,
    command: str | None = None,
    reverted: bool = False,
) -> bool:
    """Record what became of a claimed update; False when an outcome already exists."""
    return bool(
        conn.execute(
            text(
                "INSERT INTO inbound_outcome (work_item_id, update_id, outcome, reason_code, "
                "reason, command, reverted, at) VALUES (:i, :u, :o, :rc, :r, :c, :rv, :n) "
                "ON CONFLICT (work_item_id, update_id) DO NOTHING"
            ),
            {
                "i": work_item_id,
                "u": update_id,
                "o": outcome,
                "rc": reason_code,
                "r": None if reason is None else reason[:2000],
                "c": command,
                "rv": reverted,
                "n": now,
            },
        ).rowcount
    )


def unresolved_claims(conn: Connection) -> list[Claim]:
    """Claimed updates with no outcome (the process stopped between the two, research R-07)."""
    return [
        Claim(int(r[0]), int(r[1]), int(r[2]), str(r[3]), r[4], str(r[5]), r[6])
        for r in conn.execute(
            text(
                "SELECT c.work_item_id, c.update_id, c.rev, c.changer, c.account_name, c.kind, "
                "c.object_id FROM inbound_change c LEFT JOIN inbound_outcome o "
                "ON o.work_item_id = c.work_item_id AND o.update_id = c.update_id "
                "WHERE o.work_item_id IS NULL ORDER BY c.read_at, c.work_item_id, c.update_id"
            )
        )
    ]


def outcome_counts(conn: Connection) -> dict[str, Any]:
    refused = {
        str(r[0]): int(r[1])
        for r in conn.execute(
            text(
                "SELECT reason_code, count(*) FROM inbound_outcome WHERE outcome = 'refused' "
                "GROUP BY reason_code ORDER BY reason_code"
            )
        )
    }
    reverted = int(
        conn.execute(text("SELECT count(*) FROM inbound_outcome WHERE reverted")).scalar_one()
    )
    return {"refused_by_reason": refused, "reverted": reverted}


def activity_with_source(conn: Connection, work_item_id: int, update_id: int) -> bool:
    """True when a command from this board update is already recorded by the platform (R-07)."""
    source = {"board_item": work_item_id, "update": update_id}
    for (detail,) in conn.execute(
        text("SELECT detail FROM run_activity WHERE detail LIKE :p"),
        {"p": f'%"board_item": {work_item_id}%'},
    ):
        if (_json(detail) or {}).get("source") == source:
            return True
    for (payload,) in conn.execute(
        text("SELECT payload FROM outbox_event WHERE payload LIKE :p"),
        {"p": f'%"board_item": {work_item_id}%'},
    ):
        if (_json(payload) or {}).get("source") == source:
            return True
    return False


# ------------------------------------------------------------------------------- reconciliation


def insert_reconciliation(
    conn: Connection,
    started_by: str,
    started_at: datetime,
    ended_at: datetime,
    outcome: str,
    items_checked: int,
    created_items: int,
    differences: list[dict[str, Any]],
    error: str | None = None,
) -> int:
    row = conn.execute(
        text(
            "INSERT INTO board_reconciliation (started_by, started_at, ended_at, outcome, "
            "items_checked, created_items, differences, error) "
            "VALUES (:b, :s, :e, :o, :c, :ci, :d, :err) RETURNING board_reconciliation_id"
        ),
        {
            "b": started_by,
            "s": started_at,
            "e": ended_at,
            "o": outcome,
            "c": items_checked,
            "ci": created_items,
            "d": json.dumps(differences),
            "err": None if error is None else error[:2000],
        },
    ).one()
    return int(row[0])


def reconciliation(conn: Connection, reconciliation_id: int | None = None) -> dict[str, Any] | None:
    """One reconciliation by id, or the latest when ``reconciliation_id`` is None."""
    sql = (
        "SELECT board_reconciliation_id, started_by, started_at, ended_at, outcome, "
        "items_checked, created_items, differences, error FROM board_reconciliation "
    )
    if reconciliation_id is None:
        row = conn.execute(text(sql + "ORDER BY board_reconciliation_id DESC LIMIT 1")).first()
    else:
        row = conn.execute(
            text(sql + "WHERE board_reconciliation_id = :i"), {"i": reconciliation_id}
        ).first()
    if row is None:
        return None
    return {
        "id": int(row[0]),
        "started_by": row[1],
        "started_at": row[2],
        "ended_at": row[3],
        "outcome": row[4],
        "items_checked": int(row[5]),
        "created_items": int(row[6]),
        "differences": _json(row[7]) or [],
        "error": row[8],
    }
