"""Deny-by-default authentication (FR-021, constitution XI).

Implemented as middleware rather than a route dependency so that every path, including
framework-provided ones such as ``/docs`` and ``/openapi.json`` and paths added by later
features, needs a valid session unless it is in the closed public allowlist.
"""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from adlc.identity.protocol import IdentityProvider, NotAuthenticated, Person

PUBLIC_PATHS = frozenset({"/health", "/auth/sign-in"})
NOT_AUTHENTICATED = {"kind": "not_signed_in", "detail": "not authenticated"}  # 007 FR-021


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def install_auth(app: FastAPI, provider: IdentityProvider) -> None:
    app.state.identity = provider

    @app.middleware("http")
    async def require_session(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        token = bearer_token(request)
        if token is None:
            return JSONResponse(NOT_AUTHENTICATED, status_code=401)
        try:
            person = provider.current_person(token)
        except NotAuthenticated:
            return JSONResponse(NOT_AUTHENTICATED, status_code=401)
        request.state.person = person
        request.state.token = token
        return await call_next(request)


def current_person(request: Request) -> Person:
    person: Person = request.state.person
    return person
