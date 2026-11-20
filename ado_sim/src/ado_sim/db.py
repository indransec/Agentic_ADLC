"""The simulator's SQLite file: connections, transactions and migrations (research R-04).

Every write runs in ``BEGIN IMMEDIATE`` so writers queue on the database lock instead of
failing on upgrade; reads use a plain ``BEGIN`` so they see one consistent snapshot. Times are
ISO 8601 text in UTC with microseconds, so text order is time order.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from importlib import resources
from pathlib import Path

TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def format_time(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime(TIME_FORMAT)


def parse_time(text: str) -> datetime:
    return datetime.strptime(text, TIME_FORMAT).replace(tzinfo=UTC)


def utc_now() -> str:
    return format_time(datetime.now(UTC))


def later_than(previous: str | None, candidate: str) -> str:
    """``candidate`` if it is after ``previous``, else ``previous`` plus one microsecond (R-06)."""
    if previous is None or candidate > previous:
        return candidate
    return format_time(parse_time(previous) + timedelta(microseconds=1))


class DatabaseMissingError(RuntimeError):
    """The data file does not exist (``serve`` never creates it; ``migrate`` does)."""


class Database:
    """One SQLite file; one connection per thread, closed together by :meth:`close`."""

    def __init__(self, path: Path, busy_timeout_seconds: float = 30.0, *, create: bool = False):
        self.path = path
        self.busy_timeout_seconds = busy_timeout_seconds
        if not create and not path.exists():
            raise DatabaseMissingError(f"no simulator database at {path}; run `ado-sim migrate`")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._all: list[sqlite3.Connection] = []
        self._lock = threading.Lock()

    def _connection(self) -> sqlite3.Connection:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                f"{self.path.resolve().as_uri()}?mode=rwc",
                uri=True,
                timeout=self.busy_timeout_seconds,
                isolation_level=None,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(f"PRAGMA busy_timeout={int(self.busy_timeout_seconds * 1000)}")
            self._local.conn = conn
            with self._lock:
                self._all.append(conn)
        return conn

    @contextmanager
    def write(self) -> Iterator[sqlite3.Connection]:
        conn = self._connection()
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        conn = self._connection()
        conn.execute("BEGIN")
        try:
            yield conn
        finally:
            conn.execute("COMMIT")

    def close(self) -> None:
        with self._lock:
            for conn in self._all:
                conn.close()
            self._all.clear()
        self._local = threading.local()


def _migrations() -> list[tuple[int, str]]:
    folder = resources.files("ado_sim") / "migrations"
    found = []
    for entry in folder.iterdir():
        name = entry.name
        if name.endswith(".sql") and name[:4].isdigit():
            found.append((int(name[:4]), entry.read_text(encoding="utf-8")))
    return sorted(found)


LATEST_VERSION = max(version for version, _ in _migrations())


def schema_version(db: Database) -> int:
    with db.read() as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
        ).fetchone()
        if not exists:
            return 0
        row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
        return int(row["v"] or 0)


def migrate(db: Database) -> list[int]:
    """Apply pending migrations in order; returns the versions applied."""
    conn = db._connection()
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    current = schema_version(db)
    applied = []
    for version, script in _migrations():
        if version <= current:
            continue
        conn.executescript(
            f"BEGIN IMMEDIATE;\n{script}\n"
            f"INSERT INTO schema_version (version) VALUES ({version});\nCOMMIT;"  # noqa: S608
        )
        applied.append(version)
    return applied


def drop_everything(db: Database) -> None:
    """Remove every table (used only by ``reset``; append-only rows go with their tables)."""
    conn = db._connection()
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        names = [
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for name in names:
            conn.execute(f'DROP TABLE IF EXISTS "{name}"')  # noqa: S608 (names from sqlite_master)
        conn.execute("COMMIT")
    finally:
        conn.execute("PRAGMA foreign_keys=ON")
