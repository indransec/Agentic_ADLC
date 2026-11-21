"""017 T009: page sessions and CSRF (FR-003, FR-004, FR-004a; research R-02, R-04)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ado_sim.db import Database
from ado_sim.pages import sessions
from ado_sim.process import identity_by_name
from tests.conftest import OWNER


def _owner(db: Database):  # type: ignore[no-untyped-def]
    with db.read() as conn:
        found = identity_by_name(conn, OWNER)
    assert found is not None
    return found


def test_create_and_read(db: Database) -> None:
    session_id = sessions.create(db, _owner(db), ttl_seconds=3600)
    assert len(session_id) >= 40
    with db.read() as conn:
        stored = [r[0] for r in conn.execute("SELECT session_hash FROM page_session")]
    assert stored and session_id not in stored  # only the hash is kept
    found = sessions.read(db, session_id)
    assert found is not None and found.identity.unique_name == OWNER and found.csrf_token


def test_expired_and_unknown(db: Database) -> None:
    session_id = sessions.create(db, _owner(db), ttl_seconds=3600)
    later = datetime.now(UTC) + timedelta(hours=2)
    assert sessions.read(db, session_id, now=later) is None
    assert sessions.read(db, "not-a-session") is None
    assert sessions.read(db, "") is None


def test_revoke_and_revoke_all(db: Database) -> None:
    owner = _owner(db)
    first = sessions.create(db, owner, ttl_seconds=3600)
    second = sessions.create(db, owner, ttl_seconds=3600)
    sessions.revoke(db, first)
    assert sessions.read(db, first) is None and sessions.read(db, second) is not None
    assert sessions.revoke_all(db, owner.id) == 1
    assert sessions.read(db, second) is None


def test_csrf(db: Database) -> None:
    session_id = sessions.create(db, _owner(db), ttl_seconds=3600)
    found = sessions.read(db, session_id)
    assert found is not None
    assert sessions.csrf_ok(found.csrf_token, found.csrf_token)
    assert not sessions.csrf_ok(found.csrf_token, "x")
    assert not sessions.csrf_ok(found.csrf_token, None)


def test_housekeeping(db: Database) -> None:
    owner = _owner(db)
    sessions.revoke(db, sessions.create(db, owner, ttl_seconds=3600))
    sessions.create(db, owner, ttl_seconds=1)
    live = sessions.create(db, owner, ttl_seconds=3600)
    removed = sessions.housekeeping(db, now=datetime.now(UTC) + timedelta(seconds=10))
    assert removed == 2 and sessions.read(db, live) is not None
