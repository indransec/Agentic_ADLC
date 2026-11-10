"""The versioned use-case profile (contracts/profile.md; FR-013 to FR-015; research R-06).

Each close with ``pass`` or ``exception`` and emitted values writes a new version: the previous
values with the emitted names replaced (tables replaced whole). Each run records the version
current when it opened and reads that version, even if a newer one appears.
"""

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import Connection, Engine, text

from adlc.orchestration.tracing import span

PROFILE_STATUSES = ("pass", "exception")


def merge(previous: Mapping[str, Any], emitted: Mapping[str, Any]) -> dict[str, Any]:
    return {**dict(previous), **dict(emitted)}


def proposed_parameter(value: Any) -> Any:
    """A profile value as a guardrail proposal: a plain value, or a mapping's ``value``."""
    if isinstance(value, Mapping) and "value" in value:
        return value["value"]
    return value


def current_version(conn: Connection, usecase_id: str) -> tuple[int, dict[str, Any]]:
    row = conn.execute(
        text(
            "SELECT version, profile_values FROM ledger.profile_version WHERE usecase_id = :u "
            "ORDER BY version DESC LIMIT 1"
        ),
        {"u": usecase_id},
    ).first()
    return (0, {}) if row is None else (int(row[0]), dict(row[1]))


def version_values(conn: Connection, usecase_id: str, version: int) -> dict[str, Any]:
    if version <= 0:
        return {}
    row = conn.execute(
        text(
            "SELECT profile_values FROM ledger.profile_version WHERE usecase_id = :u "
            "AND version = :v"
        ),
        {"u": usecase_id, "v": version},
    ).first()
    return {} if row is None else dict(row[0])


def on_close(
    conn: Connection, usecase_id: str, run_id: str, status: str, emitted: Mapping[str, Any]
) -> int | None:
    """Write the next profile version for a pass or exception with emitted values."""
    if status not in PROFILE_STATUSES or not emitted:
        return None
    with span("ledger", "profile_version", run_id=run_id, usecase_id=usecase_id):
        number, values = current_version(conn, usecase_id)
        conn.execute(
            text(
                "INSERT INTO ledger.profile_version (usecase_id, version, profile_values, "
                "source_run_id) VALUES (:u, :v, CAST(:p AS jsonb), :r)"
            ),
            {
                "u": usecase_id,
                "v": number + 1,
                "p": json.dumps(merge(values, emitted), default=str),
                "r": run_id,
            },
        )
    return number + 1


def history(conn: Connection, usecase_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT version, profile_values, source_run_id, created_at FROM ledger.profile_version "
            "WHERE usecase_id = :u ORDER BY version"
        ),
        {"u": usecase_id},
    ).mappings()
    return [dict(r) for r in rows]


class SqlProfileSource:
    """Feature 004's ``ProfileSource``: the values of the version a run opened with."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def values(self, usecase_id: str, run_id: str | None = None) -> Mapping[str, Any]:
        with self.engine.connect() as conn:
            if run_id is None:
                return current_version(conn, usecase_id)[1]
            version = conn.execute(
                text("SELECT profile_version FROM run.terminal_run WHERE run_id = :r"),
                {"r": run_id},
            ).scalar()
            if version is None:
                return current_version(conn, usecase_id)[1]
            return version_values(conn, usecase_id, int(version))
