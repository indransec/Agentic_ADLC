"""The SQLite engine set-up (adlc.db.engine): typed values, locking, independent writes."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import Engine, event, text

from adlc.db.engine import database_engine, parse_time, time_text, write_independently

TABLE = (
    "CREATE TABLE sample (id INTEGER PRIMARY KEY AUTOINCREMENT, at timestamptz NOT NULL "
    "DEFAULT (now()), day date, body jsonb, flag boolean, cost numeric(14, 6), ref uuid, "
    "code text CHECK (code IS NULL OR code REGEXP '^[A-Z]{2}$'))"
)


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    built = database_engine(tmp_path / "t.db", timedelta(seconds=1), create=True)
    with built.begin() as conn:
        conn.execute(text(TABLE))
    return built


def test_values_come_back_typed(engine: Engine) -> None:
    ref = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sample (day, body, flag, cost, ref, code) "
                "VALUES (:d, :b, :f, :c, :r, 'AB')"
            ),
            {
                "d": date(2026, 11, 19),
                "b": {"a": [1, 2]},
                "f": True,
                "c": Decimal("0.012345"),
                "r": ref,
            },
        )
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM sample")).mappings().one()
        latest = conn.execute(text('SELECT max(at) AS "at [timestamptz]" FROM sample')).scalar()
    assert row["at"].tzinfo is UTC and latest == row["at"]
    assert row["day"] == date(2026, 11, 19)
    assert row["body"] == {"a": [1, 2]} and row["flag"] is True
    assert row["cost"] == Decimal("0.012345") and row["ref"] == ref


def test_times_sort_as_text() -> None:
    early = datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC)
    late = early + timedelta(microseconds=1)
    assert time_text(early) < time_text(late)
    assert parse_time(time_text(late)) == late
    assert parse_time("2026-01-01 09:00:00") == early  # SQLite's own format, read as UTC


def test_checks_use_regexp(engine: Engine) -> None:
    with pytest.raises(Exception, match="CHECK"), engine.begin() as conn:
        conn.execute(text("INSERT INTO sample (code) VALUES ('abc')"))


def test_explicit_transactions_take_the_write_lock_reads_do_not(engine: Engine) -> None:
    begins: list[str] = []
    event.listen(
        engine,
        "before_cursor_execute",
        lambda _c, _cur, statement, *_a: (
            begins.append(statement) if statement.startswith("BEGIN") else None
        ),
    )
    with engine.begin() as conn:
        conn.execute(text("SELECT 1"))
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    assert begins == ["BEGIN IMMEDIATE", "BEGIN"]


def test_a_read_inside_a_write_does_not_wait(engine: Engine) -> None:
    with engine.begin() as writing:
        writing.execute(text("INSERT INTO sample (code) VALUES ('AB')"))
        with engine.connect() as reading:  # sees the last committed state, at once
            assert reading.execute(text("SELECT count(*) FROM sample")).scalar() == 0


def _count(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text("SELECT count(*) FROM sample")).scalar_one())


def _insert(engine: Engine, code: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO sample (code) VALUES (:c)"), {"c": code})


def test_independent_write_runs_at_once_outside_a_transaction(engine: Engine) -> None:
    write_independently(engine, lambda: _insert(engine, "AA"))
    assert _count(engine) == 1


def test_independent_write_waits_for_the_writer_then_survives_its_rollback(
    engine: Engine,
) -> None:
    with pytest.raises(RuntimeError), engine.begin() as conn:
        conn.execute(text("INSERT INTO sample (code) VALUES ('BB')"))
        write_independently(engine, lambda: _insert(engine, "CC"))
        assert _count(engine) == 0  # not yet: the writer holds the lock
        raise RuntimeError("the caller's action fails")
    with engine.connect() as conn:
        codes = [r[0] for r in conn.execute(text("SELECT code FROM sample"))]
    assert codes == ["CC"]  # the independent write stood on its own


def test_independent_write_after_commit(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO sample (code) VALUES ('DD')"))
        write_independently(engine, lambda: _insert(engine, "EE"))
    assert _count(engine) == 2
