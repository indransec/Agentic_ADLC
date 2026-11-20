import sqlite3
import threading
import time
from pathlib import Path

import pytest

from ado_sim.db import (
    LATEST_VERSION,
    Database,
    DatabaseMissingError,
    drop_everything,
    later_than,
    migrate,
    schema_version,
    utc_now,
)


def test_missing_file_is_refused_unless_created(tmp_path: Path) -> None:
    with pytest.raises(DatabaseMissingError):
        Database(tmp_path / "none.db")
    db = Database(tmp_path / "sub" / "new.db", create=True)
    migrate(db)
    assert (tmp_path / "sub" / "new.db").exists()
    db.close()


def test_wal_and_foreign_keys(tmp_path: Path) -> None:
    db = Database(tmp_path / "a.db", create=True)
    with db.read() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    db.close()


def test_migrations_are_idempotent(tmp_path: Path) -> None:
    db = Database(tmp_path / "a.db", create=True)
    assert migrate(db) == list(range(1, LATEST_VERSION + 1))
    assert migrate(db) == []
    assert schema_version(db) == LATEST_VERSION
    db.close()


def test_write_rolls_back_on_error(tmp_path: Path) -> None:
    db = Database(tmp_path / "a.db", create=True)
    migrate(db)
    with pytest.raises(RuntimeError), db.write() as conn:
        conn.execute("INSERT INTO organization (id, name) VALUES ('o', 'org')")
        raise RuntimeError("boom")
    with db.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM organization").fetchone()[0] == 0
    db.close()


def test_writers_are_serialised(tmp_path: Path) -> None:
    db = Database(tmp_path / "a.db", create=True)
    migrate(db)
    order: list[str] = []
    entered = threading.Event()

    def first() -> None:
        with db.write():
            entered.set()
            time.sleep(0.2)
            order.append("first")

    def second() -> None:
        entered.wait()
        with db.write():
            order.append("second")

    threads = [threading.Thread(target=first), threading.Thread(target=second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert order == ["first", "second"]
    db.close()


def test_drop_everything(tmp_path: Path) -> None:
    db = Database(tmp_path / "a.db", create=True)
    migrate(db)
    drop_everything(db)
    assert schema_version(db) == 0
    db.close()


def test_times() -> None:
    now = utc_now()
    assert now.endswith("Z") and len(now) == len("2026-11-20T10:15:30.123456Z")
    assert later_than(None, now) == now
    assert later_than("2026-11-20T10:15:30.123456Z", "2026-11-20T10:15:30.123456Z") == (
        "2026-11-20T10:15:30.123457Z"
    )
    assert later_than("2026-11-20T10:15:30.123456Z", "2026-11-20T10:15:29.000000Z") == (
        "2026-11-20T10:15:30.123457Z"
    )
    assert later_than("2026-11-20T10:15:30.123456Z", "2026-11-20T10:15:31.000000Z") == (
        "2026-11-20T10:15:31.000000Z"
    )


def test_sqlite_errors_are_sqlite_errors(tmp_path: Path) -> None:
    db = Database(tmp_path / "a.db", create=True)
    migrate(db)
    with pytest.raises(sqlite3.IntegrityError), db.write() as conn:
        conn.execute("INSERT INTO project (id, organization_id, name) VALUES ('p', 'x', 'n')")
    db.close()
