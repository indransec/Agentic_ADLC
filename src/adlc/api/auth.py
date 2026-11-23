"""Deny-by-default authentication (FR-021, constitution XI).

Implemented as middleware rather than a route dependency so that every path, including
framework-provided ones such as ``/docs`` and ``/openapi.json`` and paths added by later
features, needs a valid session unless it is in the closed public allowlist.

A session arrives one of two ways (feature 022, contracts/session.md):

- ``Authorization: Bearer <token>``: tools, tests and pilot processes, as before. It wins when
  both are present, and needs no CSRF value (a browser never attaches it on its own).
- the HttpOnly cookie ``adlc_session`` that cookie-mode sign-in sets for the browser. Page
  scripts cannot read it. A changing request (not GET, HEAD or OPTIONS) that relies on it must
  carry ``X-ADLC-CSRF`` with the value bound to that session (:func:`csrf_value`); other origins,
  including other ports on the same host, cannot learn that value (research R-02).
"""

import base64
import hashlib
import hmac
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from adlc.identity.protocol import IdentityProvider, NotAuthenticated, Person

PUBLIC_PATHS = frozenset({"/health", "/auth/sign-in"})
NOT_AUTHENTICATED = {"kind": "not_signed_in", "detail": "not authenticated"}  # 007 FR-021
CROSS_SITE = {"kind": "not_allowed", "detail": "cross-site request refused"}  # 022 FR-014
SESSION_COOKIE = "adlc_session"
CSRF_HEADER = "x-adlc-csrf"
SIGN_IN_CSRF = "sign-in"  # the value cookie-mode sign-in carries (it has no session yet)
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

Via = Literal["bearer", "cookie"]


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def csrf_value(secret: str, token: str) -> str:
    """The CSRF value of one session: an HMAC of its token under the session secret."""
    digest = hmac.new(secret.encode(), b"csrf\0" + token.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def csrf_ok(request: Request, secret: str, token: str) -> bool:
    given = request.headers.get(CSRF_HEADER, "")
    return bool(given) and hmac.compare_digest(given, csrf_value(secret, token))


def is_https(request: Request) -> bool:
    """The original scheme: the request's own, or the one adlc-web forwarded."""
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return request.url.scheme == "https" or forwarded == "https"


def install_auth(app: FastAPI, provider: IdentityProvider, session_secret: str) -> None:
    app.state.identity = provider
    app.state.csrf_secret = session_secret

    @app.middleware("http")
    async def require_session(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        via: Via = "bearer"
        token = bearer_token(request)
        if token is None:
            via = "cookie"
            token = request.cookies.get(SESSION_COOKIE) or None
        if token is None:
            return JSONResponse(NOT_AUTHENTICATED, status_code=401)
        try:
            person = provider.current_person(token)
        except NotAuthenticated:
            return JSONResponse(NOT_AUTHENTICATED, status_code=401)
        if (
            via == "cookie"
            and request.method not in SAFE_METHODS
            and not csrf_ok(request, session_secret, token)
        ):
            return JSONResponse(CROSS_SITE, status_code=403)
        request.state.person = person
        request.state.token = token
        request.state.session_via = via
        return await call_next(request)


def current_person(request: Request) -> Person:
    person: Person = request.state.person
    return person
