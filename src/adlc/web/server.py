"""``adlc-web``: the built browser application, and ``/api`` forwarded to the platform API
(feature 022; contracts/web-server.md, research R-03, R-11, R-12).

The browser reaches one origin. Everything under ``/api`` goes to the platform API unchanged
(same method, path, query and body), with request and answer headers taken from allowlists, so
the platform's own paths, its public paths and its sessions are untouched and no CORS is ever
needed. Every other GET is the application's page or one of its built files. This process holds
no session and no secret; it imports only ``adlc.web`` and ``adlc.config``.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http.cookiejar import CookieJar, DefaultCookiePolicy
from pathlib import Path
from typing import Any

import httpx
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from adlc.config.settings import UiSettings

log = logging.getLogger("adlc.web")
# httpx logs every request's full URL, query string included, at INFO: kept to warnings, so the
# logs hold only what SecurityHeaders records (method, path, status)
QUIET_LOGGERS = ("httpx", "httpcore")

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; "
    "frame-ancestors 'none'; form-action 'self'"
)
SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"content-security-policy", CSP.encode()),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"same-origin"),
    (b"cross-origin-opener-policy", b"same-origin"),
)
REQUEST_HEADERS = frozenset({"cookie", "content-type", "content-length", "accept", "x-adlc-csrf"})
ANSWER_HEADERS = frozenset(
    {
        "set-cookie",
        "content-type",
        "content-disposition",
        "cache-control",
        "content-length",
        "x-content-type-options",
    }
)
UNAVAILABLE = {"kind": "unavailable", "detail": "the platform could not be reached"}
IMMUTABLE = "public, max-age=31536000, immutable"
TIMEOUT = httpx.Timeout(60.0, connect=5.0)


class SecurityHeaders:
    """Sets the security headers on every answer, drops any CORS header, and logs method, path
    (never the query) and status; headers and bodies are never logged."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                kept = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if not k.lower().startswith(b"access-control-")
                    and k.lower() not in {name for name, _ in SECURITY_HEADERS}
                ]
                message["headers"] = kept + list(SECURITY_HEADERS)
                log.info("%s %s %s", scope["method"], scope["path"], message["status"])
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BuiltAssets(StaticFiles):
    """The hashed build files: cached for a year, since a new build has new names."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code in (200, 304):
            response.headers["cache-control"] = IMMUTABLE
        return response


async def _body(answer: httpx.Response) -> AsyncIterator[bytes]:
    """The answer's bytes as they arrive; an answer already read (in memory) in one piece."""
    if answer.is_stream_consumed:
        yield answer.content
        return
    async for chunk in answer.aiter_raw():
        yield chunk


def create_app(
    settings: UiSettings, transport: httpx.AsyncBaseTransport | None = None
) -> Starlette:
    """The ui process. ``transport`` replaces the network to the API (tests only)."""
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    dist = Path(settings.ui_dist_dir)
    index = dist / "index.html"
    api_url = settings.api_url.rstrip("/")
    refresh = max(1, round(settings.ui_dashboard_refresh.total_seconds()))
    state: dict[str, httpx.AsyncClient] = {}

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        # The proxy must never remember a cookie: one person's session would be sent with
        # everyone's requests. A jar whose policy accepts no domain stores nothing (passed
        # as the CookieJar itself: httpx.Cookies(jar) would copy it into a default jar).
        jar = CookieJar(policy=DefaultCookiePolicy(allowed_domains=[]))
        async with httpx.AsyncClient(transport=transport, timeout=TIMEOUT, cookies=jar) as client:
            state["client"] = client
            yield

    async def forward(request: Request) -> Response:
        raw_path: bytes = request.scope.get("raw_path") or request.url.path.encode()
        path = raw_path.decode("latin-1").removeprefix("/api")
        query = request.scope.get("query_string", b"").decode("latin-1")
        url = f"{api_url}{path or '/'}" + (f"?{query}" if query else "")
        headers = {k: v for k, v in request.headers.items() if k.lower() in REQUEST_HEADERS}
        headers["x-forwarded-proto"] = request.url.scheme
        headers["x-forwarded-host"] = request.headers.get("host", "")
        client = state["client"]
        outgoing = client.build_request(
            request.method, url, headers=headers, content=request.stream()
        )
        try:
            answer = await client.send(outgoing, stream=True)
        except httpx.TransportError:
            return JSONResponse(UNAVAILABLE, status_code=502)
        kept = [(k, v) for k, v in answer.headers.multi_items() if k.lower() in ANSWER_HEADERS]
        response = StreamingResponse(
            _body(answer), status_code=answer.status_code, background=BackgroundTask(answer.aclose)
        )
        response.raw_headers = [(k.lower().encode(), v.encode("latin-1")) for k, v in kept]
        return response

    async def config(request: Request) -> Response:
        body: dict[str, Any] = {"env": settings.env, "dashboard_refresh_seconds": refresh}
        return JSONResponse(body, headers={"cache-control": "no-store"})

    async def health(request: Request) -> Response:
        if index.is_file():
            return JSONResponse({"status": "ok"})
        return JSONResponse({"status": "missing build"}, status_code=503)

    top_level = {f.name for f in dist.iterdir() if f.is_file()} if dist.is_dir() else set()

    async def page(request: Request) -> Response:
        name = request.path_params["path"]
        if name in top_level and name != "index.html":  # the build's own files (logo, icon)
            return FileResponse(dist / name, headers={"cache-control": "no-cache"})
        if not index.is_file():
            return JSONResponse({"status": "missing build"}, status_code=503)
        return FileResponse(index, headers={"cache-control": "no-cache"})

    routes = [
        Route(
            "/api/{path:path}",
            forward,
            methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        ),
        Route("/config.json", config, methods=["GET"]),
        Route("/health", health, methods=["GET"]),
        Mount("/assets", app=BuiltAssets(directory=dist / "assets", check_dir=False)),
        Route("/{path:path}", page, methods=["GET", "HEAD"]),
    ]
    app = Starlette(routes=routes, lifespan=lifespan)
    app.add_middleware(SecurityHeaders)
    return app
