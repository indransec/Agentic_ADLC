"""The data store: one SQLite file shared by every platform process.

Every connection is set up the same way (``_on_connect``):

- write-ahead logging, so readers never wait for a writer, and enforced foreign keys;
- a busy timeout (``ADLC_DB_BUSY_TIMEOUT``): a write waits for another process's write;
- a transaction begun explicitly (``engine.begin()``, ``connection.begin()``) starts with
  ``BEGIN IMMEDIATE``: it takes the write lock up front, so two workers can never claim the same
  outbox event, timer or run (what ``FOR UPDATE SKIP LOCKED`` did on Postgres), at the cost of
  one writer at a time. A connection that only reads (``engine.connect()``, begun implicitly)
  starts with a plain ``BEGIN``: it reads the last committed state without the write lock, so a
  read on a second connection never waits for the transaction that is writing;
- a write that must stand on its own (an audit row kept even if the caller's action fails, as a
  second Postgres connection used to give) goes through ``write_independently``: run at once,
  or, while this thread's transaction holds the write lock, right after that transaction ends;
- the SQL functions the schema uses: ``now()`` (UTC, microseconds) and ``regexp`` (for the
  ``REGEXP`` checks);
- typed values: columns declared ``timestamptz``, ``date``, ``jsonb``, ``boolean``, ``numeric``
  or ``uuid`` come back as ``datetime``, ``date``, JSON values, ``bool``, ``Decimal`` and
  ``UUID``; an expression is typed with a column alias such as ``AS "at [timestamptz]"``.
  Python values go in the same way (lists and dicts are stored as JSON text).

Times are stored as ISO 8601 text in UTC with microseconds, so text order is time order.
"""

import functools
import json
import logging
import re
import sqlite3
import sys
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import FrameType
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.exc import OperationalError

from adlc.config.settings import DatabaseSettings

log = logging.getLogger(__name__)

TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f+00:00"
# unixepoch(..., 'subsec') needs 3.42; the JSON operators 3.38; IS DISTINCT FROM 3.39
MIN_SQLITE = (3, 42, 0)


class ConfigurationError(RuntimeError):
    """A setting needed for this operation is missing."""


class DatabaseUnavailable(RuntimeError):
    """The data store did not answer within the configured timeout."""


# ------------------------------------------------------------------------------ values


def time_text(value: datetime) -> str:
    """A time as stored: UTC, microseconds, fixed width (naive times are taken as UTC)."""
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).strftime(TIME_FORMAT)


def parse_time(raw: bytes | str) -> datetime:
    value = raw.decode() if isinstance(raw, bytes) else raw
    parsed = datetime.fromisoformat(value.replace(" ", "T", 1) if "T" not in value else value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return time_text(value)
    if isinstance(value, date | uuid.UUID | Decimal):
        return str(value)
    raise TypeError(f"{type(value).__name__} is not JSON serialisable")


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def _register_types() -> None:
    """Process-wide sqlite3 adapters (Python -> SQL) and converters (declared type -> Python)."""
    sqlite3.register_adapter(datetime, time_text)
    sqlite3.register_adapter(date, date.isoformat)
    sqlite3.register_adapter(Decimal, str)
    sqlite3.register_adapter(uuid.UUID, str)
    for kind in (dict, list, tuple):
        sqlite3.register_adapter(kind, _json_text)
    sqlite3.register_converter("timestamptz", parse_time)
    sqlite3.register_converter("date", lambda raw: date.fromisoformat(raw.decode()))
    sqlite3.register_converter("jsonb", lambda raw: json.loads(raw.decode()))
    sqlite3.register_converter("boolean", lambda raw: raw not in (b"0", b""))
    sqlite3.register_converter("numeric", lambda raw: Decimal(raw.decode()))
    sqlite3.register_converter("uuid", lambda raw: uuid.UUID(raw.decode()))


_register_types()


# ------------------------------------------------------------------------- functions


def _now() -> str:
    return time_text(datetime.now(UTC))


@functools.lru_cache(maxsize=256)
def _pattern(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


def _regexp(pattern: str | None, value: Any) -> bool | None:
    if pattern is None or value is None:
        return None
    return _pattern(pattern).search(str(value)) is not None


# ---------------------------------------------------------------------------- engine


def _url(path: Path, *, create: bool) -> str:
    mode = "rwc" if create else "rw"  # services never create the file: the migrations do
    return f"sqlite+pysqlite:///file:{path}?mode={mode}&uri=true"


def database_engine(path: Path, busy_timeout: timedelta, *, create: bool = False) -> Engine:
    """An engine on the platform database file, set up as the module docstring describes."""
    if sqlite3.sqlite_version_info < MIN_SQLITE:
        raise ConfigurationError(
            f"SQLite {sqlite3.sqlite_version} is too old; the platform needs "
            f"{'.'.join(map(str, MIN_SQLITE))} or later (use Python from uv or the API image)"
        )
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        _url(path, create=create),
        connect_args={
            "detect_types": sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            "timeout": busy_timeout.total_seconds(),
            "check_same_thread": False,
        },
    )
    busy_ms = int(busy_timeout.total_seconds() * 1000)

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: sqlite3.Connection, _record: Any) -> None:
        dbapi_connection.isolation_level = None  # transactions are begun below, not by sqlite3
        dbapi_connection.create_function("now", 0, _now)
        dbapi_connection.create_function("regexp", 2, _regexp, deterministic=True)
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA synchronous = NORMAL")
            cursor.execute(f"PRAGMA busy_timeout = {busy_ms}")
        finally:
            cursor.close()

    @event.listens_for(engine, "begin")
    def _on_begin(connection: Any) -> None:
        implicit = _implicit_begin()
        connection.exec_driver_sql("BEGIN" if implicit else "BEGIN IMMEDIATE")
        if not implicit:
            _writers(engine).add(id(connection.connection.dbapi_connection))

    @event.listens_for(engine, "before_cursor_execute")
    def _on_execute(
        connection: Any, _cursor: Any, statement: str, *_args: Any
    ) -> None:  # a plain BEGIN takes the write lock at its first write
        if connection.in_transaction() and _WRITE.match(statement):
            _writers(engine).add(id(connection.connection.dbapi_connection))

    def _ended(connection: Any) -> None:
        _writers(engine).discard(id(connection.connection.dbapi_connection))

    event.listen(engine, "commit", _ended)
    event.listen(engine, "rollback", _ended)

    @event.listens_for(engine.pool, "checkin")
    def _on_checkin(dbapi_connection: Any, _record: Any) -> None:
        if dbapi_connection is not None:
            _writers(engine).discard(id(dbapi_connection))
        _flush(engine)

    return engine


# ------------------------------------------------------------------ independent writes

_WRITE = re.compile(r"\s*(INSERT|UPDATE|DELETE|REPLACE|CREATE|DROP|ALTER)\b", re.IGNORECASE)
_threads = threading.local()


def _state(engine: Engine) -> dict[str, Any]:
    states: dict[int, dict[str, Any]] = _threads.__dict__.setdefault("states", {})
    return states.setdefault(id(engine), {"writers": set(), "pending": [], "flushing": False})


def _writers(engine: Engine) -> set[int]:
    found: set[int] = _state(engine)["writers"]
    return found


def write_independently(engine: Engine, write: Callable[[], None]) -> None:
    """Run ``write`` (which opens its own transaction) so that it never waits for this thread.

    At once when this thread holds no write transaction on ``engine``; otherwise right after
    that transaction ends, whether it commits or rolls back (SQLite has one writer, so a second
    connection writing now would wait for the first until the busy timeout).
    """
    state = _state(engine)
    if state["writers"]:
        state["pending"].append(write)
    else:
        write()


def _flush(engine: Engine) -> None:
    state = _state(engine)
    if state["writers"] or state["flushing"]:
        return
    state["flushing"] = True
    try:
        while state["pending"] and not state["writers"]:
            write = state["pending"].pop(0)
            try:
                write()
            except Exception:  # a connection is being returned: never raise from here
                log.exception("deferred independent write failed")
    finally:
        state["flushing"] = False


def _implicit_begin() -> bool:
    """True when SQLAlchemy began this transaction implicitly (the first statement on a
    connection from ``engine.connect()``), not through an explicit ``begin()``."""
    frame: FrameType | None = sys._getframe(2)
    for _ in range(6):
        if frame is None:
            return False
        if frame.f_code.co_name == "_autobegin":
            return True
        frame = frame.f_back
    return False


def open_engine(settings: DatabaseSettings, *, create: bool = False) -> Engine:
    """The engine every platform process uses; ``create`` only for the migrations."""
    return database_engine(settings.db_path, settings.db_busy_timeout, create=create)


def wait_for_database(engine: Engine, timeout: timedelta, interval: float = 1.0) -> None:
    """Retry ``SELECT 1`` until the database file exists and answers, or ``timeout`` passes."""
    deadline = time.monotonic() + timeout.total_seconds()
    target = str(engine.url.database).removeprefix("file:")
    while True:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return
        except OperationalError:
            if time.monotonic() >= deadline:
                raise DatabaseUnavailable(
                    f"database at {target} not reachable within {int(timeout.total_seconds())}s"
                ) from None
            log.info("waiting for database at %s", target)
            time.sleep(interval)
