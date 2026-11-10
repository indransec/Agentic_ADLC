"""US2 core rule (constitution V, IX): ledger rows are append-only for every identity.

FR-011, SC-004, spec clarification 1.
"""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
APPEND_ONLY = "ledger.ledger_record is append-only"

MUTATIONS = {
    "update": "UPDATE ledger.ledger_record SET ledger_key = 'changed'",
    "delete": "DELETE FROM ledger.ledger_record",
    "truncate": "TRUNCATE ledger.ledger_record",
}


def _insert(engine: Engine, key: str = "UC-0001/T0/run-1", content_hash: str = HASH_A) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ledger.ledger_record (ledger_key, content_hash, previous_record_hash) "
                "VALUES (:key, :hash, NULL)"
            ),
            {"key": key, "hash": content_hash},
        )


def _rows(engine: Engine) -> list[tuple[str, str]]:
    with engine.connect() as conn:
        return [
            (row.ledger_key, row.content_hash)
            for row in conn.execute(
                text("SELECT ledger_key, content_hash FROM ledger.ledger_record ORDER BY 1")
            )
        ]


def test_app_can_insert_and_read(app_engine: Engine) -> None:
    _insert(app_engine)
    assert _rows(app_engine) == [("UC-0001/T0/run-1", HASH_A)]


@pytest.mark.parametrize("mutation", sorted(MUTATIONS))
def test_app_identity_is_refused(app_engine: Engine, mutation: str) -> None:
    _insert(app_engine)
    with pytest.raises(ProgrammingError), app_engine.begin() as conn:
        conn.execute(text(MUTATIONS[mutation]))
    assert _rows(app_engine) == [("UC-0001/T0/run-1", HASH_A)]


@pytest.mark.parametrize("mutation", sorted(MUTATIONS))
def test_owner_identity_is_refused(app_engine: Engine, owner_engine: Engine, mutation: str) -> None:
    _insert(app_engine)
    with pytest.raises(DBAPIError) as excinfo, owner_engine.begin() as conn:
        conn.execute(text(MUTATIONS[mutation]))
    orig = excinfo.value.orig
    assert getattr(orig, "sqlstate", None) == "42501"
    assert APPEND_ONLY in str(orig)
    assert _rows(owner_engine) == [("UC-0001/T0/run-1", HASH_A)]


@pytest.mark.parametrize("bad", ["sha256:xyz", "md5:" + "a" * 64, "sha256:" + "A" * 64, ""])
def test_content_hash_format_enforced(app_engine: Engine, bad: str) -> None:
    with pytest.raises(IntegrityError):
        _insert(app_engine, content_hash=bad)


def test_previous_hash_nullable_but_format_enforced(app_engine: Engine) -> None:
    with app_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ledger.ledger_record (ledger_key, content_hash, previous_record_hash) "
                "VALUES ('k/1', :a, :b)"
            ),
            {"a": HASH_A, "b": HASH_B},
        )
    with pytest.raises(IntegrityError), app_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ledger.ledger_record (ledger_key, content_hash, previous_record_hash) "
                "VALUES ('k/2', :a, 'not-a-hash')"
            ),
            {"a": HASH_A},
        )


def test_duplicate_ledger_key_rejected(app_engine: Engine) -> None:
    _insert(app_engine)
    with pytest.raises(IntegrityError):
        _insert(app_engine, content_hash=HASH_B)


def test_app_has_no_privileges_beyond_ledger_record(app_engine: Engine) -> None:
    with app_engine.connect() as conn:
        grants = conn.execute(
            text(
                "SELECT table_schema || '.' || table_name, privilege_type "
                "FROM information_schema.role_table_grants WHERE grantee = current_user"
            )
        ).all()
        create_rights = conn.execute(
            text(
                "SELECT n.nspname FROM pg_namespace n "
                "WHERE n.nspname IN ('spec','run','ledger','events','public') "
                "AND has_schema_privilege(current_user, n.oid, 'CREATE')"
            )
        ).all()
    writes = sorted(g for g in grants if g[1] != "SELECT")
    reads = {table for table, privilege in grants if privilege == "SELECT"}
    assert writes == [("ledger.ledger_record", "INSERT")]
    # Feature 002 adds read-only access to the spec registry; nothing else is readable.
    assert all(t == "ledger.ledger_record" or t.startswith("spec.") for t in reads), reads
    assert create_rights == []
