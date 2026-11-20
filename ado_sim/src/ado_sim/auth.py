"""Personal access tokens: issue, revoke, list, authenticate (research R-09, FR-015).

Tokens are 52 random characters, shown once and stored only as HMAC-SHA256 under
``ADO_SIM_TOKEN_KEY``. Requests use Basic auth (any user name, the token as password) or Bearer.
Every failure looks the same to the caller.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
from dataclasses import dataclass

from ado_sim.db import Database, utc_now
from ado_sim.process import Identity, identity_by_id

TOKEN_LENGTH = 52
_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"


class TokenError(ValueError):
    """A token command was refused (unknown identity)."""


@dataclass(frozen=True)
class TokenInfo:
    id: int
    unique_name: str
    label: str
    issued_at: str
    revoked_at: str | None


def new_token() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(TOKEN_LENGTH))


def hash_token(key: str, token: str) -> str:
    return hmac.new(key.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def issue(db: Database, key: str, unique_name: str, label: str = "") -> tuple[int, str]:
    """Create a token for an identity; the token is returned once and never stored."""
    token = new_token()
    with db.write() as conn:
        row = conn.execute(
            "SELECT id FROM identity WHERE unique_name = ? COLLATE NOCASE", (unique_name,)
        ).fetchone()
        if row is None:
            raise TokenError(f"no identity with unique name {unique_name}")
        cursor = conn.execute(
            "INSERT INTO access_token (identity_id, token_hash, label, issued_at)"
            " VALUES (?, ?, ?, ?)",
            (row["id"], hash_token(key, token), label, utc_now()),
        )
        return int(cursor.lastrowid or 0), token


def revoke(db: Database, token_id: int) -> bool:
    with db.write() as conn:
        cursor = conn.execute(
            "UPDATE access_token SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
            (utc_now(), token_id),
        )
        return cursor.rowcount == 1


def list_tokens(db: Database, unique_name: str | None = None) -> list[TokenInfo]:
    query = (
        "SELECT t.id, i.unique_name, t.label, t.issued_at, t.revoked_at FROM access_token t"
        " JOIN identity i ON i.id = t.identity_id"
    )
    params: tuple[str, ...] = ()
    if unique_name is not None:
        query += " WHERE i.unique_name = ? COLLATE NOCASE"
        params = (unique_name,)
    with db.read() as conn:
        return [
            TokenInfo(r["id"], r["unique_name"], r["label"], r["issued_at"], r["revoked_at"])
            for r in conn.execute(query + " ORDER BY t.id", params)
        ]


def token_from_header(header: str | None) -> str | None:
    if not header:
        return None
    scheme, _, credentials = header.strip().partition(" ")
    credentials = credentials.strip()
    if not credentials:
        return None
    if scheme.lower() == "bearer":
        return credentials
    if scheme.lower() == "basic":
        try:
            decoded = base64.b64decode(credentials, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return None
        _, colon, token = decoded.partition(":")
        return token if colon and token else None
    return None


def authenticate(db: Database, key: str, header: str | None) -> Identity | None:
    """The active identity a request's Authorization header names, or None."""
    token = token_from_header(header)
    if token is None:
        return None
    candidate = hash_token(key, token)
    with db.read() as conn:
        row = conn.execute(
            "SELECT identity_id, token_hash FROM access_token"
            " WHERE token_hash = ? AND revoked_at IS NULL",
            (candidate,),
        ).fetchone()
        if row is None or not hmac.compare_digest(row["token_hash"], candidate):
            return None
        identity = identity_by_id(conn, row["identity_id"])
    return identity if identity is not None and identity.active else None
