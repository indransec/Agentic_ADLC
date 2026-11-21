"""Page sign-in: a seeded user and one of three credentials (017 FR-002; research R-03).

1. a page password, set by the operator, stored only as an scrypt hash;
2. the shared demo password, only when ``ADO_SIM_DEMO_PASSWORD`` is set;
3. one of the user's active personal access tokens.

A credential only ever signs in the user picked; the service account never signs in. Every
failure raises the same message after comparable work (a dummy scrypt when the user has no page
password), so neither the message nor the timing tells which part was wrong.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from ado_sim import auth
from ado_sim.db import Database, utc_now
from ado_sim.process import Identity, identity_by_name, is_service

REFUSED = "The user or the password is not right."
MIN_PASSWORD_LENGTH = 12
_N, _R, _P, _SALT, _KEY = 2**15, 8, 1, 16, 32
_MAXMEM = 128 * _N * _R * 2
_DUMMY = None  # a hash computed once, checked when the user has no page password


class SignInRefused(Exception):  # noqa: N818 - a refusal the caller expects, not a fault
    def __init__(self) -> None:
        super().__init__(REFUSED)


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT)
    key = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_KEY, maxmem=_MAXMEM)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(key)}"


def check_password(password: str, stored: str) -> bool:
    try:
        kind, n, r, p, salt, expected = stored.split("$")
        if kind != "scrypt":
            return False
        want = base64.b64decode(expected)
        got = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(want),
            maxmem=128 * int(n) * int(r) * 2,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, want)


def _dummy() -> str:
    global _DUMMY  # noqa: PLW0603 - computed once on first use
    if _DUMMY is None:
        _DUMMY = hash_password(secrets.token_urlsafe(16))
    return _DUMMY


def _person(db: Database, unique_name: str) -> Identity | None:
    with db.read() as conn:
        identity = identity_by_name(conn, unique_name) if unique_name.strip() else None
        if identity is None or not identity.active or is_service(conn, identity):
            return None
        return identity


def set_password(db: Database, unique_name: str, password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"a page password needs at least {MIN_PASSWORD_LENGTH} characters")
    identity = _person(db, unique_name)
    if identity is None:
        raise ValueError(
            f"{unique_name} is not a user who can sign in (unknown, or the service account)"
        )
    stored = hash_password(password)
    with db.write() as conn:
        conn.execute(
            "INSERT INTO page_password (identity_id, password_hash, set_at) VALUES (?, ?, ?)"
            " ON CONFLICT (identity_id) DO UPDATE SET password_hash = excluded.password_hash,"
            " set_at = excluded.set_at",
            (identity.id, stored, utc_now()),
        )


def clear_password(db: Database, unique_name: str) -> bool:
    """Remove a user's page password and end their page sessions (FR-004a)."""
    from ado_sim.pages.sessions import revoke_all  # noqa: PLC0415 - avoids an import cycle

    identity = _person(db, unique_name)
    if identity is None:
        return False
    with db.write() as conn:
        removed = conn.execute(
            "DELETE FROM page_password WHERE identity_id = ?", (identity.id,)
        ).rowcount
    revoke_all(db, identity.id)
    return removed == 1


def sign_in(
    db: Database, token_key: str, unique_name: str, credential: str, *, demo_password: str | None
) -> Identity:
    """The user picked, if ``credential`` is one of theirs; else ``SignInRefused``."""
    identity = _person(db, unique_name)
    stored = None
    if identity is not None:
        with db.read() as conn:
            row = conn.execute(
                "SELECT password_hash FROM page_password WHERE identity_id = ?", (identity.id,)
            ).fetchone()
        stored = row[0] if row else None
    password_ok = check_password(credential, stored or _dummy()) and stored is not None
    demo_ok = demo_password is not None and hmac.compare_digest(
        credential.encode(), demo_password.encode()
    )
    header = "Basic " + base64.b64encode(f":{credential}".encode()).decode()
    token_identity = auth.authenticate(db, token_key, header) if credential else None
    token_ok = (
        token_identity is not None and identity is not None and token_identity.id == identity.id
    )
    if identity is None or not (password_ok or demo_ok or token_ok):
        raise SignInRefused
    return identity
