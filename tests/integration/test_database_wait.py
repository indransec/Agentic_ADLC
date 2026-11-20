"""US1 edge case: a service waits a bounded time for the data store, then names it."""

import time
from datetime import timedelta
from pathlib import Path

import pytest

from adlc.db.engine import DatabaseUnavailable, database_engine, wait_for_database


def test_missing_database_times_out_with_named_target(tmp_path: Path) -> None:
    missing = tmp_path / "not-migrated" / "adlc.db"
    engine = database_engine(missing, timedelta(seconds=1))
    started = time.monotonic()
    with pytest.raises(DatabaseUnavailable) as excinfo:
        wait_for_database(engine, timedelta(seconds=2), interval=0.2)
    assert time.monotonic() - started < 5
    assert str(missing) in str(excinfo.value)
    assert not missing.exists()  # a service never creates the database; the migrations do


def test_waits_until_the_migrations_create_the_file(tmp_path: Path) -> None:
    path = tmp_path / "adlc.db"
    creator = database_engine(path, timedelta(seconds=1), create=True)
    with creator.connect():
        pass  # connecting creates the file, as the migrations do
    creator.dispose()
    wait_for_database(database_engine(path, timedelta(seconds=1)), timedelta(seconds=2))
