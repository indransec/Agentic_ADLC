"""Knowledge tools: the agents' grounding over the knowledge MCP server (008 research R-02).

A ``KnowledgeTool`` is one operation (``search`` or ``read``) of one source. It passes on only the
arguments the model may set, adds the terminal's grounding scope and maximum data class from the
pinned spec, calls the server and records every result as a retrieval. The tool gate has already
authorized the call (feature 004). Nothing here names a terminal, role or source.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol

import anyio
import httpx

from adlc.agents.catalogue import AgentCatalogue
from adlc.agents.tools import Tool, ToolContext
from adlc.orchestration import spec_view

OPERATIONS: Mapping[str, Mapping[str, str]] = {
    "search": {
        "query": "what to look for (1 to 500 characters)",
        "limit": "how many results, 1 to 10 (default 5)",
    },
    "read": {
        "document": "a document path from a search result",
        "section": "a section from a search result; leave out for the document's outline",
    },
}
DESCRIPTIONS = {
    "search": "Search the {source} knowledge source within your terminal's grounding scope. "
    "Results are passages with a source, document, section and content hash you can cite.",
    "read": "Read a document of the {source} knowledge source, or one of its sections.",
}
PERMISSION_PREFIX = "mcp"
TIMEOUT_S = 10.0
REQUEST_MAX = 500


class KnowledgeUnavailable(Exception):
    """The knowledge server could not be reached or answered with a server error."""


@dataclass(frozen=True)
class Retrieval:
    source: str
    operation: str
    request: str
    document: str
    section: str
    content_hash: str
    data_class: str
    synthetic: bool
    retrieval_id: int | None = None

    def with_id(self, retrieval_id: int) -> "Retrieval":
        return replace(self, retrieval_id=retrieval_id)


class RetrievalLog(Protocol):
    def record(self, context: ToolContext, found: Sequence[Retrieval]) -> list[Retrieval]: ...

    def for_attempt(self, run_id: str, attempt: int) -> list[Retrieval]: ...


class KnowledgeCaller(Protocol):
    def __call__(
        self, source: str, tool: str, arguments: Mapping[str, Any]
    ) -> tuple[bool, Any]: ...


def grounding_scope(spec: Mapping[str, Any], source: str) -> list[str]:
    """The terminal's grounding scope items for one source, as written in the spec."""
    grounding = (spec_view.body(spec).get("playbooks") or {}).get("grounding") or []
    return [str(g.get("scope", "")) for g in grounding if str(g.get("mcp")) == source]


def max_class(spec: Mapping[str, Any]) -> str:
    access = (spec_view.body(spec).get("authorities") or {}).get("data_access") or {}
    return str(access.get("max_class") or "")


class KnowledgeTool:
    def __init__(
        self, source: str, operation: str, caller: KnowledgeCaller, log: RetrievalLog
    ) -> None:
        if operation not in OPERATIONS:
            raise ValueError(f"unknown knowledge operation {operation}")
        self.source, self.operation, self.caller, self.log = source, operation, caller, log

    @property
    def name(self) -> str:
        return f"{self.source}_{self.operation}"

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": DESCRIPTIONS[self.operation].format(source=self.source),
            "arguments": dict(OPERATIONS[self.operation]),
        }

    def call(self, arguments: Mapping[str, Any], context: ToolContext) -> str:
        scope = grounding_scope(context.spec, self.source)
        if not scope:
            return (
                f"There is no grounding scope for {self.source} in this terminal; "
                "nothing to search."
            )
        allowed = {k: v for k, v in arguments.items() if k in OPERATIONS[self.operation]}
        try:
            failed, payload = self.caller(
                self.source,
                self.operation,
                {**allowed, "scope": scope, "max_class": max_class(context.spec)},
            )
        except KnowledgeUnavailable:
            return f"knowledge source unavailable: {self.source}"
        if failed:
            return f"{self.name} failed: {payload}"
        found = self._retrievals(allowed, payload)
        if found:
            self.log.record(context, found)
        return json.dumps(payload, ensure_ascii=False)

    def _retrievals(self, arguments: Mapping[str, Any], payload: Any) -> list[Retrieval]:
        if not isinstance(payload, Mapping):
            return []
        if self.operation == "search":
            request = str(arguments.get("query", ""))
            items = payload.get("results") or []
        else:
            request = str(arguments.get("document", ""))
            items = [payload]
        return [
            Retrieval(
                source=self.source,
                operation=self.operation,
                request=request[:REQUEST_MAX],
                document=str(item.get("document", "")),
                section=str(item.get("section", "")),
                content_hash=str(item.get("content_hash", "")),
                data_class=str(item.get("data_class", "")),
                synthetic=bool(item.get("synthetic", False)),
            )
            for item in items
            if isinstance(item, Mapping) and item.get("document") and item.get("content_hash")
        ]


def knowledge_tools(
    agents: AgentCatalogue, caller: KnowledgeCaller, log: RetrievalLog
) -> dict[str, Tool]:
    """A tool for every binding ``<source>_<operation>`` with permission ``mcp:<source>:read``."""
    tools: dict[str, Tool] = {}
    for agent in agents.agents.values():
        for binding in agent.tools:
            prefix, _, rest = binding.permission.partition(":")
            source = rest.partition(":")[0]
            operation = binding.tool.removeprefix(f"{source}_")
            if (
                prefix == PERMISSION_PREFIX
                and operation in OPERATIONS
                and binding.tool != operation
            ):
                tools[binding.tool] = KnowledgeTool(source, operation, caller, log)
    return tools


class McpCaller:
    """Calls ``<url>/mcp/<source>/`` through the MCP streamable-HTTP client."""

    def __init__(self, url: str, token: str, timeout_s: float = TIMEOUT_S) -> None:
        self.url, self.token, self.timeout_s = url.rstrip("/"), token, timeout_s

    def __call__(self, source: str, tool: str, arguments: Mapping[str, Any]) -> tuple[bool, Any]:
        try:
            return anyio.run(self._call, source, tool, dict(arguments))
        except Exception as exc:  # connection, timeout, HTTP or protocol failure
            raise KnowledgeUnavailable(source) from exc

    async def _call(self, source: str, tool: str, arguments: dict[str, Any]) -> tuple[bool, Any]:
        from mcp import ClientSession  # noqa: PLC0415 - only processes that ground load MCP
        from mcp.client.streamable_http import streamable_http_client  # noqa: PLC0415

        headers = {"Authorization": f"Bearer {self.token}"}
        with anyio.fail_after(self.timeout_s):
            async with (
                httpx.AsyncClient(headers=headers, timeout=self.timeout_s) as http,
                streamable_http_client(f"{self.url}/mcp/{source}/", http_client=http) as streams,
                ClientSession(streams[0], streams[1]) as session,
            ):
                await session.initialize()
                result = await session.call_tool(tool, arguments)
        text = "".join(getattr(c, "text", "") for c in result.content)
        if result.isError:
            return True, text
        try:
            return False, json.loads(text)
        except json.JSONDecodeError:
            return False, text
