"""Authorization decisions (contracts/authorization.md; FR-015 to FR-017; constitution IV).

Pure: given the actor, the request and the run's terminal spec, decide in this order:
run scope, tool scopes (deny still applies), deny list, allow list, default deny.
"""

import fnmatch
from collections.abc import Mapping
from typing import Any

from adlc.orchestration import spec_view

TOOL_PREFIX = "mcp:"


def request(action: str, resource: str) -> str:
    return f"{action}:{resource}" if resource else action


def _patterns(spec: Mapping[str, Any] | None, key: str) -> list[str]:
    if spec is None:
        return []
    authorities = spec_view.body(spec).get("authorities") or {}
    raw = authorities.get(key) or []
    return [_normalise(str(p)) for p in raw]


def _normalise(pattern: str) -> str:
    # Spec convention: "<verb>:<area>.all" means everything in the area.
    return pattern[: -len(".all")] + ".*" if pattern.endswith(".all") else pattern


def _matches(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        if fnmatch.fnmatchcase(text, pattern):
            return pattern
    return None


def bound_run(actor: str) -> str | None:
    kind, sep, run = actor.partition(":")
    return run if sep and kind and run else None


def decide(
    actor: str, action: str, resource: str, run_id: str | None, spec: Mapping[str, Any] | None
) -> tuple[bool, str]:
    wanted = request(action, resource)
    actor_run = bound_run(actor)
    if run_id is None or actor_run != run_id:
        return False, f"out of scope: {actor} is bound to {actor_run or 'no run'}"
    denied = _matches(wanted, _patterns(spec, "deny"))
    if denied is not None:
        return False, f"denied by {denied}"
    if wanted.startswith(TOOL_PREFIX):
        scope = _matches(wanted, _patterns(spec, "tool_scopes"))
        if scope is None:
            return False, f"tool not in scope: {wanted}"
        return True, f"allowed by tool scope {scope}"
    allowed = _matches(wanted, _patterns(spec, "allow"))
    if allowed is not None:
        return True, f"allowed by {allowed}"
    return False, f"no allow entry matches {wanted}"
