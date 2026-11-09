"""US1 edge case: the API waits a bounded time for the data store, then names it."""

import time
from datetime import timedelta

import pytest
from sqlalchemy import create_engine

from adlc.db.engine import DatabaseUnavailable, wait_for_database

PASSWORD = "wait-test-password-value"


def test_unreachable_database_times_out_with_named_target() -> None:
    engine = create_engine(
        f"postgresql+psycopg://adlc_app:{PASSWORD}@127.0.0.1:1/adlc",
        connect_args={"connect_timeout": 1},
    )
    started = time.monotonic()
    with pytest.raises(DatabaseUnavailable) as excinfo:
        wait_for_database(engine, timedelta(seconds=2), interval=0.2)
    assert time.monotonic() - started < 5
    assert "127.0.0.1:1" in str(excinfo.value)
    assert PASSWORD not in str(excinfo.value)
