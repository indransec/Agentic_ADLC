"""The knowledge MCP server (008 research R-01, contracts/knowledge-mcp.md).

One MCP endpoint per source folder at ``/mcp/<source>/`` (streamable HTTP, stateless, JSON
responses), each with ``search`` and ``read``. The platform adds ``scope`` (the terminal's
grounding items for that source) and ``max_class``; the server enforces both again. Every MCP
request needs the service token. Logs hold request counts only, never content.
"""

import contextlib
import hmac
import json
import logging
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from ruamel.yaml import YAML
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from adlc.config.settings import KnowledgeSettings
from adlc.knowledge.documents import Document, load_folder
from adlc.knowledge.scope import Scope, class_allowed
from adlc.knowledge.search import Index, read_section

log = logging.getLogger("adlc.knowledge")
DEFAULT_LIMIT = 5
QUERY_MAX = 500


def data_class_ranks(spec_dir: Path) -> dict[str, int]:
    data = YAML(typ="safe").load((spec_dir / "shared" / "data_classes.yaml").read_text())
    return {str(d["id"]): int(d["rank"]) for d in data.get("data_classes") or []}


class Knowledge:
    """The searchable folder and the rules every tool call follows."""

    def __init__(self, folder: Path, ranks: Mapping[str, int]) -> None:
        self.ranks = dict(ranks)
        self.documents = load_folder(folder, self.ranks)
        self.index = Index(self.documents)
        self.sources = sorted({d.source for d in self.documents})
        self.requests: Counter[str] = Counter()

    def allowed(self, source: str, scope: list[str], max_class: str) -> Callable[[Document], bool]:
        parsed = Scope.parse(scope)

        def check(doc: Document) -> bool:
            return (
                doc.source == source
                and parsed.contains(doc)
                and class_allowed(doc.data_class, max_class, self.ranks)
            )

        return check

    def search(
        self, source: str, query: str, limit: int, scope: list[str], max_class: str
    ) -> dict[str, Any]:
        self.requests[f"{source}.search"] += 1
        if not query.strip() or len(query) > QUERY_MAX:
            raise ToolError("invalid arguments: query must be 1 to 500 characters")
        hits = self.index.search(query, self.allowed(source, scope, max_class), limit)
        return {
            "results": [
                {
                    "source": h.document.source,
                    "document": h.document.path,
                    "section": h.section.section,
                    "title": h.document.title,
                    "snippet": h.snippet,
                    "content_hash": h.section.content_hash,
                    "data_class": h.document.data_class,
                    "synthetic": h.document.synthetic,
                }
                for h in hits
            ],
            "note": f"{len(hits)} results in scope",
        }

    def read(
        self, source: str, document: str, section: str | None, scope: list[str], max_class: str
    ) -> dict[str, Any]:
        self.requests[f"{source}.read"] += 1
        doc = self.index.document(source, document)
        if doc is None:
            raise ToolError(f"not found: {document}")
        if not self.allowed(source, scope, max_class)(doc):
            raise ToolError(f"out of scope: {document}")
        found = read_section(doc, section)
        if found is None:
            raise ToolError(f"not found: section {section!r} of {document}")
        return {
            "source": source,
            "document": doc.path,
            "section": section or "",
            "title": doc.title,
            "text": found.text,
            "content_hash": found.content_hash,
            "data_class": doc.data_class,
            "synthetic": doc.synthetic,
            "cut": found.cut,
        }


def source_server(knowledge: Knowledge, source: str, allowed_hosts: list[str]) -> FastMCP:
    server = FastMCP(
        f"knowledge-{source}",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True, allowed_hosts=allowed_hosts
        ),
    )

    @server.tool(name="search", description=f"Search the {source} knowledge source.")
    def search(
        query: str, limit: int = DEFAULT_LIMIT, scope: list[str] | None = None, max_class: str = ""
    ) -> str:
        return json.dumps(knowledge.search(source, query, limit, scope or [], max_class))

    @server.tool(name="read", description=f"Read a document or a section of {source}.")
    def read(
        document: str,
        section: str | None = None,
        scope: list[str] | None = None,
        max_class: str = "",
    ) -> str:
        return json.dumps(knowledge.read(source, document, section, scope or [], max_class))

    return server


def build_app(settings: KnowledgeSettings) -> Starlette:
    knowledge = Knowledge(settings.knowledge_dir, data_class_ranks(settings.spec_dir))
    hosts = [h.strip() for h in settings.knowledge_allowed_hosts.split(",") if h.strip()]
    servers = {source: source_server(knowledge, source, hosts) for source in knowledge.sources}
    token = settings.knowledge_token.get_secret_value()

    async def health(request: Request) -> Response:
        return JSONResponse(
            {"status": "ok", "sources": knowledge.sources, "documents": len(knowledge.documents)}
        )

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with contextlib.AsyncExitStack() as stack:
            for server in servers.values():
                await stack.enter_async_context(server.session_manager.run())
            log.info(
                "knowledge server ready: %d sources, %d documents",
                len(servers),
                len(knowledge.documents),
            )
            yield
            log.info("knowledge requests: %s", dict(knowledge.requests))

    routes: list[Route | Mount] = [Route("/health", health)]
    routes += [
        Mount(f"/mcp/{s}", app=server.streamable_http_app()) for s, server in servers.items()
    ]
    app = Starlette(routes=routes, lifespan=lifespan)

    async def require_token(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path.startswith("/mcp"):
            given = request.headers.get("authorization", "")
            if not hmac.compare_digest(given.encode(), f"Bearer {token}".encode()):
                return JSONResponse({"detail": "not authenticated"}, status_code=401)
        return await call_next(request)

    app.add_middleware(BaseHTTPMiddleware, dispatch=require_token)

    app.state.knowledge = knowledge
    return app
