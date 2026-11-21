"""Page sessions and CSRF (017 FR-003, FR-004, FR-004a; research R-02, R-04).

The cookie holds a random session id; the database keeps only its SHA-256 with the identity, an
absolute expiry and a CSRF token. Sign-out revokes one session; clearing a page password or
revoking a token revokes all of the user's sessions.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ado_sim.db import Database, format_time
from ado_sim.process import Identity, identity_by_id

COOKIE = "ado_sim_session"


@dataclass(frozen=True)
class PageSession:
    identity: Identity
    csrf_token: str
    expires_at: str


def _hash(session_id: str) -> str:
    return hashlib.sha256(session_id.encode()).hexdigest()


def create(db: Database, identity: Identity, *, ttl_seconds: float) -> str:
    session_id = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    with db.write() as conn:
        conn.execute(
            "INSERT INTO page_session (session_hash, identity_id, csrf_token, created_at,"
            " expires_at) VALUES (?, ?, ?, ?, ?)",
            (
                _hash(session_id),
                identity.id,
                secrets.token_urlsafe(32),
                format_time(now),
                format_time(now + timedelta(seconds=ttl_seconds)),
            ),
        )
    return session_id


def read(
    db: Database, session_id: str | None, *, now: datetime | None = None
) -> PageSession | None:
    if not session_id:
        return None
    moment = format_time(now or datetime.now(UTC))
    with db.read() as conn:
        row = conn.execute(
            "SELECT identity_id, csrf_token, expires_at FROM page_session"
            " WHERE session_hash = ? AND revoked_at IS NULL AND expires_at > ?",
            (_hash(session_id), moment),
        ).fetchone()
        if row is None:
            return None
        identity = identity_by_id(conn, row["identity_id"])
    if identity is None or not identity.active:
        return None
    return PageSession(identity, row["csrf_token"], row["expires_at"])


def revoke(db: Database, session_id: str | None) -> None:
    if not session_id:
        return
    with db.write() as conn:
        conn.execute(
            "UPDATE page_session SET revoked_at = ? WHERE session_hash = ? AND revoked_at IS NULL",
            (format_time(datetime.now(UTC)), _hash(session_id)),
        )


def revoke_all(db: Database, identity_id: str) -> int:
    with db.write() as conn:
        return conn.execute(
            "UPDATE page_session SET revoked_at = ? WHERE identity_id = ? AND revoked_at IS NULL",
            (format_time(datetime.now(UTC)), identity_id),
        ).rowcount


def csrf_ok(expected: str, given: str | None) -> bool:
    return bool(given) and hmac.compare_digest(expected.encode(), str(given).encode())


def housekeeping(db: Database, *, now: datetime | None = None) -> int:
    """Remove expired and revoked sessions; returns how many."""
    moment = format_time(now or datetime.now(UTC))
    with db.write() as conn:
        return conn.execute(
            "DELETE FROM page_session WHERE revoked_at IS NOT NULL OR expires_at <= ?", (moment,)
        ).rowcount
