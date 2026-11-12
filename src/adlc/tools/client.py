"""The MCP client the platform uses to call the 010 tool servers with a per-call run token
(streamable HTTP). Shared by the agents' tools and the policy engine's pilot evidence."""

from collections.abc import Mapping
from typing import Any

import anyio
import httpx


class ToolUnavailable(Exception):
    """The server did not answer (connection, timeout, HTTP or protocol failure)."""


class McpClient:
    """Calls ``<url of host>/mcp/<server>/`` with a per-call run token (MCP streamable HTTP)."""

    def __init__(self, urls: Mapping[str, str], timeout_s: float) -> None:
        self.urls = {h: u.rstrip("/") for h, u in urls.items()}
        self.timeout_s = timeout_s

    def __call__(
        self, host: str, server: str, tool: str, arguments: Mapping[str, Any], token: str
    ) -> tuple[bool, str]:
        url = self.urls.get(host)
        if not url:
            raise ToolUnavailable(host)
        try:
            return anyio.run(self._call, f"{url}/mcp/{server}/", tool, dict(arguments), token)
        except Exception as exc:  # connection, timeout, HTTP or protocol failure
            raise ToolUnavailable(server) from exc

    async def _call(
        self, url: str, tool: str, arguments: dict[str, Any], token: str
    ) -> tuple[bool, str]:
        from mcp import ClientSession  # noqa: PLC0415 - only processes that call tools load MCP
        from mcp.client.streamable_http import streamable_http_client  # noqa: PLC0415

        headers = {"Authorization": f"Bearer {token}"}
        with anyio.fail_after(self.timeout_s):
            async with (
                httpx.AsyncClient(headers=headers, timeout=self.timeout_s) as http,
                streamable_http_client(url, http_client=http) as streams,
                ClientSession(streams[0], streams[1]) as session,
            ):
                await session.initialize()
                result = await session.call_tool(tool, arguments)
        text = "".join(getattr(c, "text", "") for c in result.content)
        return bool(result.isError), text
