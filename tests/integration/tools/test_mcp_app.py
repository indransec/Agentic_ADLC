"""T011: the shared server plumbing through the real MCP client: the token is checked for the
tool's scope and bound values before a handler runs; limits and errors map to tool errors."""

import time
from typing import Any

import pytest

from adlc.agents.mcp_tools import ToolUnavailable
from adlc.tools.catalogue import CATALOGUE
from adlc.tools.mcp_app import Call, ServerTools, ToolFailure, build_app
from tests.support.tools import ALLOWED, KEY, call, serve, token

SEEN: list[dict[str, Any]] = []


def status(call_: Call, args: dict[str, Any]) -> Any:
    SEEN.append({"tool": call_.tool.full_name, "args": args, "run": call_.claims.run_id})
    return {"stable": "sha256:" + "a" * 64}


def deploy(call_: Call, args: dict[str, Any]) -> Any:
    return {"package_hash": call_.bound("authorised_hash")}


def slow(call_: Call, args: dict[str, Any]) -> Any:
    time.sleep(3)
    return {}


def refuse(call_: Call, args: dict[str, Any]) -> Any:
    raise ToolFailure("refused: no candidate deployed")


def app(deploy_handler: Any = deploy) -> Any:
    tools = CATALOGUE.for_server("cd")
    handlers = {"cd_status": status, "cd_deploy": deploy_handler}
    return build_app("test-tools", {"cd": ServerTools(tools, handlers)}, KEY, ALLOWED)


def test_token_scope_and_bound_values_are_checked_by_the_server() -> None:
    SEEN.clear()
    with serve(app()) as base:
        assert call(base, "cd", "status", {}, token(["mcp:cd:read"])) == (
            False,
            '{"stable": "sha256:' + "a" * 64 + '"}',
        )
        failed, text = call(base, "cd", "status", {}, token(["mcp:cd:deploy"]))
        assert failed and text.startswith("not permitted") and "mcp:cd:read" in text
        failed, text = call(base, "cd", "deploy", {}, token(["mcp:cd:deploy"]))
        assert failed and "authorised_hash" in text
        failed, text = call(base, "cd", "status", {}, token(["mcp:cd:read"], now=time.time() - 400))
        assert failed and "expired" in text
        failed, text = call(base, "cd", "status", {}, token(["mcp:cd:read"], key="x" * 40))
        assert failed and "signature" in text
        good = token(["mcp:cd:deploy"], bound={"authorised_hash": "sha256:" + "b" * 64})
        assert call(base, "cd", "deploy", {}, good)[0] is False
    assert [s["tool"] for s in SEEN] == ["cd_status"]  # refused calls never reached a handler


def test_no_token_is_refused_before_mcp() -> None:
    with serve(app()) as base, pytest.raises(ToolUnavailable):
        call(base, "cd", "status", {}, "")


def test_arguments_outside_the_schema_and_tool_errors() -> None:
    with serve(app(refuse)) as base:
        failed, text = call(base, "cd", "status", {"anything": 1}, token(["mcp:cd:read"]))
        assert failed and "validation" in text.lower()
        good = token(["mcp:cd:deploy"], bound={"authorised_hash": "sha256:" + "b" * 64})
        assert call(base, "cd", "deploy", {}, good) == (True, "refused: no candidate deployed")


def test_time_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace

    tools = [
        replace(t, limit_s=0.5) if t.name == "status" else t for t in CATALOGUE.for_server("cd")
    ]
    slow_app = build_app(
        "test-tools",
        {"cd": ServerTools(tools, {"cd_status": slow, "cd_deploy": deploy})},
        KEY,
        ALLOWED,
    )
    with serve(slow_app) as base:
        failed, text = call(base, "cd", "status", {}, token(["mcp:cd:read"]))
        assert failed and text.startswith("timed out")
