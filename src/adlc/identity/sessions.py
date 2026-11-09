"""Signed, expiring session tokens and in-process revocation (research R-05).

Tokens are signed with ``itsdangerous``; expiry is checked against an injectable clock so it
is testable. Revocations live in memory: a sign-out is not remembered across API restarts
(accepted MVP limit, spec FR-021).
"""

import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from itsdangerous import BadData, URLSafeSerializer

Clock = Callable[[], datetime]
SALT = "adlc.session"


def utc_now() -> datetime:
    return datetime.now(UTC)


class SessionError(Exception):
    """The token is malformed, has a bad signature or has expired."""


@dataclass(frozen=True)
class SessionClaims:
    account_name: str
    session_id: str
    issued_at: datetime
    expires_at: datetime


class SessionSigner:
    def __init__(self, secret: str, ttl: timedelta, clock: Clock = utc_now) -> None:
        self._serializer = URLSafeSerializer(secret, salt=SALT)
        self._ttl = ttl
        self._clock = clock

    def issue(self, account_name: str) -> tuple[str, datetime]:
        issued = int(self._clock().timestamp())
        payload = {"a": account_name, "s": secrets.token_hex(16), "i": issued}
        token = self._serializer.dumps(payload)
        return str(token), datetime.fromtimestamp(issued, UTC) + self._ttl

    def verify(self, token: str) -> SessionClaims:
        try:
            payload = self._serializer.loads(token)
            account_name, session_id, issued = payload["a"], payload["s"], payload["i"]
        except (BadData, KeyError, TypeError):
            raise SessionError("invalid session token") from None
        if not isinstance(account_name, str) or not isinstance(session_id, str):
            raise SessionError("invalid session token")
        if not isinstance(issued, int):
            raise SessionError("invalid session token")
        issued_at = datetime.fromtimestamp(issued, UTC)
        expires_at = issued_at + self._ttl
        if self._clock() >= expires_at:
            raise SessionError("session expired")
        return SessionClaims(account_name, session_id, issued_at, expires_at)


class RevocationSet:
    """Session ids revoked by sign-out, kept until they would have expired anyway."""

    def __init__(self, clock: Clock = utc_now) -> None:
        self._entries: dict[str, datetime] = {}
        self._lock = threading.Lock()
        self._clock = clock

    def add(self, session_id: str, expires_at: datetime) -> None:
        with self._lock:
            self._entries[session_id] = expires_at

    def _prune(self) -> None:
        now = self._clock()
        for session_id in [s for s, expiry in self._entries.items() if expiry <= now]:
            del self._entries[session_id]

    def __contains__(self, session_id: object) -> bool:
        with self._lock:
            self._prune()
            return session_id in self._entries

    def __len__(self) -> int:
        with self._lock:
            self._prune()
            return len(self._entries)
