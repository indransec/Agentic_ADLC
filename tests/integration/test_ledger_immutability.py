"""US2 core rule (constitution V, IX): ledger rows are append-only for every connection.

FR-011, SC-004, spec clarification 1. SQLite has one database identity; triggers refuse every
change, and the hash chain detects a change made by dropping them (tests/integration/ledger).
"""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
APPEND_ONLY = "ledger_record is append-only"

MUTATIONS = {
    "update": "UPDATE ledger_record SET ledger_key = 'changed'",
    "delete": "DELETE FROM ledger_record",
    "delete one": "DELETE FROM ledger_record WHERE ledger_key = 'UC-0001/T0/run-1'",
}


def _insert(engine: Engine, key: str = "UC-0001/T0/run-1", content_hash: str = HASH_A) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ledger_record (ledger_key, content_hash, previous_record_hash) "
                "VALUES (:key, :hash, NULL)"
            ),
            {"key": key, "hash": content_hash},
        )


def _rows(engine: Engine) -> list[tuple[str, str]]:
    with engine.connect() as conn:
        return [
            (row.ledger_key, row.content_hash)
            for row in conn.execute(
                text("SELECT ledger_key, content_hash FROM ledger_record ORDER BY 1")
            )
        ]


def test_app_can_insert_and_read(app_engine: Engine) -> None:
    _insert(app_engine)
    assert _rows(app_engine) == [("UC-0001/T0/run-1", HASH_A)]


@pytest.mark.parametrize("mutation", sorted(MUTATIONS))
def test_every_change_is_refused(app_engine: Engine, mutation: str) -> None:
    _insert(app_engine)
    with pytest.raises(IntegrityError) as excinfo, app_engine.begin() as conn:
        conn.execute(text(MUTATIONS[mutation]))
    assert APPEND_ONLY in str(excinfo.value.orig)
    assert _rows(app_engine) == [("UC-0001/T0/run-1", HASH_A)]


@pytest.mark.parametrize("bad", ["sha256:xyz", "md5:" + "a" * 64, "sha256:" + "A" * 64, ""])
def test_content_hash_format_enforced(app_engine: Engine, bad: str) -> None:
    with pytest.raises(IntegrityError):
        _insert(app_engine, content_hash=bad)


def test_previous_hash_nullable_but_format_enforced(app_engine: Engine) -> None:
    with app_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ledger_record (ledger_key, content_hash, previous_record_hash) "
                "VALUES ('k/1', :a, :b)"
            ),
            {"a": HASH_A, "b": HASH_B},
        )
    with pytest.raises(IntegrityError), app_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ledger_record (ledger_key, content_hash, previous_record_hash) "
                "VALUES ('k/2', :a, 'not-a-hash')"
            ),
            {"a": HASH_A},
        )


def test_duplicate_ledger_key_rejected(app_engine: Engine) -> None:
    _insert(app_engine)
    with pytest.raises(IntegrityError):
        _insert(app_engine, content_hash=HASH_B)
