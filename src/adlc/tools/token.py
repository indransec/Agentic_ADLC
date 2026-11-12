"""Run tokens (feature 010, research R-02, contracts/run-token.md).

The platform signs one token per tool call after its tool gate allowed the call: the run, the use
case, the terminal, the terminal's ``mcp:`` scopes from the pinned spec, the values the server must
use (``bound``) and a five-minute lifetime. Servers verify it again before any tool runs. Standard
library only: HMAC-SHA256 over canonical JSON. Tokens are never logged, traced or stored, and
error messages never contain them.
"""

import base64
import hashlib
import hmac
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

VERSION = "v1"
TTL_S = 300
SKEW_S = 60
MIN_KEY = 32


class TokenError(Exception):
    """Why a token is not accepted; the message never contains the token."""


@dataclass(frozen=True)
class Claims:
    run_id: str
    usecase_id: str
    terminal_id: str
    attempt: int
    scopes: tuple[str, ...]
    bound: Mapping[str, str] = field(default_factory=dict)
    iat: int = 0
    exp: int = 0

    def as_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "usecase_id": self.usecase_id,
            "terminal_id": self.terminal_id,
            "attempt": self.attempt,
            "scopes": list(self.scopes),
            "bound": dict(self.bound),
            "iat": self.iat,
            "exp": self.exp,
        }


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _signature(payload: str, key: str) -> str:
    if len(key) < MIN_KEY:
        raise ValueError(f"the token key must have at least {MIN_KEY} characters")
    return _b64(hmac.new(key.encode(), payload.encode(), hashlib.sha256).digest())


def issue(
    *,
    run_id: str,
    usecase_id: str,
    terminal_id: str,
    attempt: int,
    scopes: Iterable[str],
    bound: Mapping[str, str] | None = None,
    now: float,
    ttl_s: int = TTL_S,
) -> Claims:
    iat = int(now)
    return Claims(
        run_id,
        usecase_id,
        terminal_id,
        attempt,
        tuple(sorted(set(scopes))),
        {k: v for k, v in (bound or {}).items() if v},
        iat,
        iat + ttl_s,
    )


def sign(claims: Claims, key: str) -> str:
    payload = f"{VERSION}.{_b64(canonical(claims.as_json()))}"
    return f"{payload}.{_signature(payload, key)}"


def verify(
    token: str, key: str, *, scope: str | None, now: float, required: Iterable[str] = ()
) -> Claims:
    """The claims, after the checks in the contract's order; ``TokenError`` otherwise.

    ``scope=None`` skips the scope check, for a tool whose scope depends on a bound value; the
    caller then checks it with :func:`require_scope`."""
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != VERSION:
        raise TokenError("malformed token")
    payload = f"{parts[0]}.{parts[1]}"
    if not hmac.compare_digest(_signature(payload, key), parts[2]):
        raise TokenError("bad signature")
    try:
        body = json.loads(_unb64(parts[1]))
        claims = Claims(
            str(body["run_id"]),
            str(body["usecase_id"]),
            str(body["terminal_id"]),
            int(body["attempt"]),
            tuple(str(s) for s in body["scopes"]),
            {str(k): str(v) for k, v in dict(body.get("bound") or {}).items()},
            int(body["iat"]),
            int(body["exp"]),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise TokenError("malformed token") from exc
    if claims.exp <= now:
        raise TokenError("token expired")
    if claims.iat > now + SKEW_S:
        raise TokenError("token issued in the future")
    if scope is not None:
        require_scope(claims, scope)
    missing = [name for name in required if not claims.bound.get(name)]
    if missing:
        raise TokenError(f"missing bound value {', '.join(missing)}")
    return claims


def require_scope(claims: Claims, scope: str) -> None:
    if scope not in claims.scopes:
        raise TokenError(f"scope {scope} not granted to this run")
