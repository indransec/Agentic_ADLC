"""Disposable platform databases for tests and ``make migration-check``.

Each database is a SQLite file in a temporary folder, migrated with the real Alembic revisions
and opened with the same engine set-up as the platform (``adlc.db.engine``).
"""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, text

from adlc.db.engine import database_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
BUSY_TIMEOUT = timedelta(seconds=10)  # a test that waits this long for a lock has deadlocked


@dataclass(frozen=True)
class PlatformDatabase:
    path: Path

    def engine(self) -> Engine:
        """An engine on this file, set up as the platform's are."""
        return database_engine(self.path, BUSY_TIMEOUT)

    @property
    def env(self) -> dict[str, str]:
        """``ADLC_*`` settings pointing at this database."""
        return {"ADLC_ENV": "dev", "ADLC_DB_PATH": str(self.path)}

    def copy_to(self, path: Path) -> "PlatformDatabase":
        """A consistent copy of this database at ``path`` (SQLite's online backup)."""
        source = sqlite3.connect(self.path)
        target = sqlite3.connect(path)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        return PlatformDatabase(path)


@contextmanager
def patched_env(values: dict[str, str]) -> Iterator[None]:
    saved = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, old in saved.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def alembic(db: PlatformDatabase, *args: str) -> None:
    """Run an Alembic command against ``db``."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(REPO_ROOT / "db" / "migrations"))
    config.attributes["skip_logging"] = True
    with patched_env(db.env):
        verb, *rest = args
        if verb == "upgrade":
            command.upgrade(config, rest[0])
        elif verb == "downgrade":
            command.downgrade(config, rest[0])
        elif verb == "stamp":
            command.stamp(config, rest[0], purge=True)
        else:
            raise ValueError(f"unsupported alembic command: {verb}")


def table_names(conn: Connection) -> set[str]:
    """Tables and views of the platform database (SQLite's own tables left out)."""
    rows = conn.execute(
        text(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
            "AND name NOT LIKE 'sqlite_%'"
        )
    )
    return {str(r[0]) for r in rows}


def column_names(conn: Connection, table: str) -> list[str]:
    """A table's columns in declaration order."""
    return [str(r[1]) for r in conn.execute(text(f"PRAGMA table_info({table})"))]


def column_info(conn: Connection, table: str) -> dict[str, tuple[str, bool, Any]]:
    """Each column's declared type, whether it is NOT NULL, and its default (as SQL text)."""
    return {
        str(r[1]): (str(r[2]).lower(), bool(r[3]), r[4])
        for r in conn.execute(text(f"PRAGMA table_info({table})"))
    }


def tamper(engine: Engine, sql: str, **params: Any) -> None:
    """Change rows past the guard triggers, as anyone with write access to the file could: drop
    every trigger, write, and put them back, in one transaction."""
    with engine.begin() as conn:
        triggers = conn.execute(
            text("SELECT name, sql FROM sqlite_master WHERE type = 'trigger'")
        ).all()
        for name, _ in triggers:
            conn.exec_driver_sql(f"DROP TRIGGER {name}")
        conn.execute(text(sql), params)
        for _, ddl in triggers:
            conn.exec_driver_sql(ddl)
