"""Feature 010 test helpers: serve a tool app on a free local port, sign run tokens and call tools
through the real MCP client."""

import threading
import time
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any

import uvicorn
from starlette.applications import Starlette

from adlc.agents.mcp_tools import McpClient
from adlc.tools.token import issue, sign
from tests.support.knowledge import free_port

KEY = "tools-test-key-" + "0" * 24
ALLOWED = ["127.0.0.1:*", "localhost:*"]


@contextmanager
def serve(app: Starlette) -> Iterator[str]:
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None, lifespan="on")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("tool server did not start")
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def token(
    scopes: Iterable[str],
    *,
    bound: Mapping[str, str] | None = None,
    run_id: str = "UC-0001/T3/run-1",
    usecase_id: str = "UC-0001",
    terminal_id: str = "T3",
    now: float | None = None,
    key: str = KEY,
) -> str:
    return sign(
        issue(
            run_id=run_id,
            usecase_id=usecase_id,
            terminal_id=terminal_id,
            attempt=1,
            scopes=scopes,
            bound=bound,
            now=time.time() if now is None else now,
        ),
        key,
    )


def call(
    base: str, server: str, tool: str, arguments: Mapping[str, Any], run_token: str
) -> tuple[bool, str]:
    return McpClient({"h": base}, 30)("h", server, tool, arguments, run_token)
