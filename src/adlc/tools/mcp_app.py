"""The MCP plumbing both tool servers share (feature 010, research R-01, R-02).

One MCP endpoint per server at ``/mcp/<server>/`` (MCP SDK low-level server, streamable HTTP,
stateless, JSON responses). Tool schemas come from the tool catalogue. Before any handler runs,
the request's run token is verified for the tool's scope and bound values; handlers run in a worker
thread under the tool's time limit. Logs and the audit hook see the tool, run and outcome only,
never arguments, results or the token.
"""

import contextlib
import functools
import json
import logging
import time
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine, Mapping
from dataclasses import dataclass
from typing import Any

import anyio
import anyio.to_thread
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.types import Receive, Scope, Send

from adlc.tools.catalogue import ToolSpec
from adlc.tools.registry import RegistryError, scope_of
from adlc.tools.token import Claims, TokenError, require_scope, verify

log = logging.getLogger("adlc.tools")
MAX_OUTPUT = 400_000  # characters of JSON a tool may return (the platform cuts what the model sees)


class ToolFailure(Exception):
    """A tool error the agent sees: ``refused: …``, ``not found: …``, ``unavailable: …``."""


@dataclass(frozen=True)
class Call:
    tool: ToolSpec
    claims: Claims

    def bound(self, name: str) -> str:
        value = self.claims.bound.get(name)
        if not value:
            raise ToolFailure(f"refused: no {name.replace('_', ' ')} for this run")
        return value


Handler = Callable[[Call, dict[str, Any]], Any]
Audit = Callable[[str, Claims | None, str], None]  # tool, claims, outcome


@dataclass(frozen=True)
class ResourceSpec:
    """A readable MCP resource (e.g. ``infra://dev``), checked against a scope like a tool."""

    uri: str
    name: str
    scope: str  # mcp:<server>:<scope>
    read: Callable[[], Any]


@dataclass(frozen=True)
class ServerTools:
    tools: list[ToolSpec]
    handlers: Mapping[str, Handler]  # by the tool's full name
    resources: tuple[ResourceSpec, ...] = ()


def _bearer(request: Request | None) -> str:
    header = "" if request is None else request.headers.get("authorization", "")
    return header[7:] if header.lower().startswith("bearer ") else ""


def _error(text: str) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)], isError=True)


def server_for(
    server_id: str,
    offered: ServerTools,
    key: str,
    *,
    clock: Callable[[], float],
    audit: Audit,
    counts: Counter[str],
) -> Server[Any, Any]:
    by_name = {t.name: t for t in offered.tools}
    server: Server[Any, Any] = Server(f"adlc-{server_id}")

    @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(name=t.name, description=t.description, inputSchema=t.input_schema())
            for t in offered.tools
        ]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def call_tool(name: str, arguments: dict[str, Any]) -> Any:
        tool = by_name.get(name)
        if tool is None:
            return _error(f"not found: tool {name}")
        request = server.request_context.request
        try:
            claims = verify(
                _bearer(request if isinstance(request, Request) else None),
                key,
                scope=None,
                now=clock(),
                required=tool.bound,
            )
            require_scope(claims, scope_of(tool, claims.bound.get("environment")))
        except (TokenError, RegistryError) as exc:
            counts[f"{tool.full_name}.refused"] += 1
            audit(tool.full_name, None, "refused")
            return _error(f"not permitted: {exc}")
        handler = offered.handlers[tool.full_name]
        try:
            with anyio.fail_after(tool.limit_s):
                result = await anyio.to_thread.run_sync(
                    functools.partial(handler, Call(tool, claims), dict(arguments)),
                    abandon_on_cancel=True,
                )
        except TimeoutError:
            outcome, reply = "timed_out", _error(f"timed out after {tool.limit_s:.0f} s")
        except ToolFailure as exc:
            outcome, reply = "failed", _error(str(exc))
        except Exception as exc:  # a bug or an unexpected system error; never its details
            log.exception("tool %s failed", tool.full_name)
            outcome, reply = "failed", _error(f"failed: {type(exc).__name__}")
        else:
            text = json.dumps(result, ensure_ascii=False, default=str)
            if len(text) > MAX_OUTPUT:
                outcome, reply = "failed", _error("failed: result too large")
            else:
                outcome = "ok"
                reply = types.CallToolResult(content=[types.TextContent(type="text", text=text)])
        counts[f"{tool.full_name}.{outcome}"] += 1
        audit(tool.full_name, claims, outcome)
        return reply

    if offered.resources:
        by_uri = {r.uri: r for r in offered.resources}

        @server.list_resources()  # type: ignore[no-untyped-call,untyped-decorator]
        async def list_resources() -> list[types.Resource]:
            return [
                types.Resource(uri=r.uri, name=r.name, mimeType="application/json")  # type: ignore[arg-type]
                for r in offered.resources
            ]

        @server.read_resource()  # type: ignore[no-untyped-call,untyped-decorator]
        async def read_resource(uri: Any) -> list[ReadResourceContents]:
            resource = by_uri.get(str(uri))
            if resource is None:
                raise ToolFailure(f"not found: resource {uri}")
            request = server.request_context.request
            try:
                verify(
                    _bearer(request if isinstance(request, Request) else None),
                    key,
                    scope=resource.scope,
                    now=clock(),
                )
            except TokenError as exc:
                audit(resource.uri, None, "refused")
                raise ToolFailure(f"not permitted: {exc}") from None
            value = await anyio.to_thread.run_sync(resource.read)
            audit(resource.uri, None, "ok")
            text = json.dumps(value, ensure_ascii=False, default=str)
            return [ReadResourceContents(content=text, mime_type="application/json")]

    return server


def build_app(
    name: str,
    servers: Mapping[str, ServerTools],
    key: str,
    allowed_hosts: list[str],
    *,
    clock: Callable[[], float] = time.time,
    audit: Audit | None = None,
    health: Callable[[], Mapping[str, Any]] | None = None,
    background: Callable[[], Coroutine[Any, Any, None]] | None = None,
) -> Starlette:
    counts: Counter[str] = Counter()
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=allowed_hosts
    )
    managers = {
        sid: StreamableHTTPSessionManager(
            app=server_for(
                sid, offered, key, clock=clock, audit=audit or (lambda *_: None), counts=counts
            ),
            json_response=True,
            stateless=True,
            security_settings=security,
        )
        for sid, offered in servers.items()
    }

    def endpoint(manager: StreamableHTTPSessionManager) -> Callable[..., Awaitable[None]]:
        async def handle(scope: Scope, receive: Receive, send: Send) -> None:
            await manager.handle_request(scope, receive, send)

        return handle

    async def health_route(request: Request) -> Response:
        return JSONResponse(
            {"status": "ok", "service": name, "servers": sorted(servers), **(health or dict)()}
        )

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with contextlib.AsyncExitStack() as stack:
            for manager in managers.values():
                await stack.enter_async_context(manager.run())
            async with anyio.create_task_group() as group:
                if background is not None:
                    group.start_soon(background)
                log.info("%s ready: %d servers", name, len(managers))
                yield
                group.cancel_scope.cancel()
            log.info("%s calls: %s", name, dict(counts))

    routes: list[Route | Mount] = [Route("/health", health_route)]
    routes += [Mount(f"/mcp/{sid}", app=endpoint(m)) for sid, m in managers.items()]
    app = Starlette(routes=routes, lifespan=lifespan)

    async def require_bearer(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path.startswith("/mcp") and not _bearer(request):
            return JSONResponse({"detail": "not authenticated"}, status_code=401)
        return await call_next(request)

    app.add_middleware(BaseHTTPMiddleware, dispatch=require_bearer)
    app.state.counts = counts
    return app
