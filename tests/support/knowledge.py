"""The knowledge MCP server for tests (feature 008): served by uvicorn on a free local port, over a
fixture folder, and an MCP client call helper."""

import json
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import anyio
import httpx
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import SecretStr

from adlc.config.settings import KnowledgeSettings
from adlc.knowledge.server import build_app
from tests.support.pg import REPO_ROOT

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "knowledge"
TOKEN = "knowledge-test-token-0001"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def knowledge_server(folder: Path = FIXTURES, token: str = TOKEN) -> Iterator[str]:
    """Serve ``folder``; yields the base URL (``http://127.0.0.1:<port>``)."""
    settings = KnowledgeSettings(
        knowledge_dir=folder,
        knowledge_token=SecretStr(token),
        spec_dir=REPO_ROOT / "adlc-specs",
    )
    port = free_port()
    config = uvicorn.Config(
        build_app(settings), host="127.0.0.1", port=port, log_config=None, lifespan="on"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("knowledge server did not start")
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def call(base: str, source: str, tool: str, arguments: dict[str, Any], token: str = TOKEN) -> Any:
    """Call one tool; returns (is_error, parsed JSON or the error text)."""

    async def run() -> tuple[bool, Any]:
        headers = {"Authorization": f"Bearer {token}"}
        async with (
            httpx.AsyncClient(headers=headers, timeout=10) as http,
            streamable_http_client(f"{base}/mcp/{source}/", http_client=http) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            result = await session.call_tool(tool, arguments)
            text = "".join(getattr(c, "text", "") for c in result.content)
            return result.isError, (text if result.isError else json.loads(text))

    return anyio.run(run)
