"""Tools on the 010 MCP servers, as the agents call them (feature 010, research R-03, R-14).

The tool gate (feature 004 ``authorize``) has already allowed the call when ``McpTool.call`` runs.
The tool then:
1. keeps only the arguments the model may set (the tool catalogue);
2. adds nothing the model chose to bind the call: the bound values (branch, environment, candidate
   and authorised hash) come from the run and the ledger, through the registry's evidence
   references, and travel in a run token signed for this one call;
3. calls ``<host url>/mcp/<server>/`` with the token;
4. records the call, and an evidence tool's result, in ``tools.*``.

A refusal by the gate is recorded too (``refused``), so every call leaves a row (FR-004).
"""

import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from adlc.agents.catalogue import AgentCatalogue
from adlc.agents.tools import Tool, ToolContext
from adlc.orchestration import spec_view
from adlc.orchestration.interfaces import EvalContext
from adlc.policy.evidence import Evidence, EvidenceProvider
from adlc.tools.catalogue import CATALOGUE, ENVIRONMENT_SCOPE, Catalogue, ToolSpec
from adlc.tools.client import ToolUnavailable
from adlc.tools.registry import ENVIRONMENT_SCOPES, TOOL_HOSTS, Registry
from adlc.tools.token import canonical, issue, sign

PERMISSION_PREFIX = "mcp"
HASH_FIELDS = ("sha256", "package_hash", "hash")
SHA = "sha256:"


def sha256_of(value: Any) -> str:
    return SHA + hashlib.sha256(canonical(value)).hexdigest()


class McpClientLike(Protocol):
    def __call__(
        self, host: str, server: str, tool: str, arguments: Mapping[str, Any], token: str
    ) -> tuple[bool, str]: ...


class ToolRecords(Protocol):
    def call(
        self,
        context: ToolContext,
        tool: ToolSpec,
        scope: str,
        arguments_sha256: str,
        outcome: str,
        reason: str,
        duration_ms: int,
    ) -> int: ...

    def result(
        self, call_id: int, context: ToolContext, kind: str, package: str | None, result: Any
    ) -> str: ...


# ------------------------------------------------------------------ bound values


def _hashes(value: Any) -> list[str]:
    """Package hashes in an artifact: a row, a list of rows or a plain value."""
    rows = value if isinstance(value, list) else [value]
    found: list[str] = []
    for row in rows:
        if isinstance(row, Mapping):
            for name in HASH_FIELDS:
                text = str(row.get(name) or "")
                if text.startswith(SHA):
                    found.append(text)
                    break
        elif isinstance(row, str) and row.startswith(SHA):
            found.append(row)
    return found


class BoundValues:
    """The values bound to a call (research R-03). Reads real evidence only: a synthetic or
    missing value binds nothing, and the tool is refused rather than guessing."""

    def __init__(self, evidence: EvidenceProvider | None, refs: Mapping[str, str]) -> None:
        self.evidence, self.refs = evidence, dict(refs)

    def _artifact(self, name: str, context: ToolContext) -> list[str]:
        ref = self.refs.get(name, "")
        terminal, _, artifact = ref.partition(".")
        if self.evidence is None or not terminal or not artifact:
            return []
        answer = self.evidence.get(
            terminal,
            EvalContext(context.terminal_id, f"bound:{name}", context.run_id, context.usecase_id),
        )
        if not isinstance(answer, Evidence) or answer.synthetic:
            return []
        record = answer.value if isinstance(answer.value, Mapping) else {}
        return _hashes(record.get(artifact))

    def candidate(self, context: ToolContext) -> str | None:
        found = set(self._artifact("candidate_hash", context))
        return found.pop() if len(found) == 1 else None

    def authorised(self, context: ToolContext) -> str | None:
        candidate = self.candidate(context)
        if candidate is None:
            return None
        matching = [h for h in self._artifact("authorised_hash", context) if h == candidate]
        return candidate if len(matching) == 1 else None

    def resolve(self, tool: ToolSpec, scope: str, context: ToolContext) -> dict[str, str | None]:
        values: dict[str, str | None] = {}
        for name in tool.bound:
            if name == "branch":
                values[name] = f"uc/{context.run_id}"
            elif name == "environment":
                values[name] = scope
            elif name == "candidate_hash":
                values[name] = self.candidate(context)
            elif name == "authorised_hash":
                values[name] = self.authorised(context)
            else:
                values[name] = None
        for name in tool.bound_optional:
            value = self.candidate(context) if name == "candidate_hash" else None
            if value:
                values[name] = value
        return values


# ------------------------------------------------------------------ the tool


def _outcome(text: str) -> str:
    lowered = text.lower()
    for prefix, outcome in (
        ("not permitted", "refused"),
        ("refused", "refused"),
        ("timed out", "timed_out"),
        ("unavailable", "unavailable"),
    ):
        if lowered.startswith(prefix):
            return outcome
    return "failed"


def mcp_scopes(spec: Mapping[str, Any]) -> list[str]:
    """The terminal's ``mcp:`` tool scopes, from the pinned spec (every mode's: the tool gate has
    already refused a scope the run's mode does not grant)."""
    return [s for s in spec_view.tool_scopes(spec, "*") if s.startswith("mcp:")]


def scope_for(spec: ToolSpec, terminal_spec: Mapping[str, Any]) -> str | None:
    """The scope a call uses: the catalogued one, or for an environment tool the one environment
    the terminal's spec grants; none or both give no scope."""
    if spec.scope != ENVIRONMENT_SCOPE:
        return spec.scope
    granted = set(mcp_scopes(terminal_spec))
    envs = [e for e in ENVIRONMENT_SCOPES if f"mcp:{spec.server}:{e}" in granted]
    return envs[0] if len(envs) == 1 else None


@dataclass
class McpTool:
    spec: ToolSpec
    host: str
    client: McpClientLike
    key: str
    bound: BoundValues
    records: ToolRecords
    now: Callable[[], float] = time.time

    @property
    def name(self) -> str:
        return self.spec.full_name

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.spec.description,
            "arguments": dict(self.spec.model_args()),
        }

    def _record(
        self, context: ToolContext, args_sha: str, outcome: str, reason: str, started: float
    ) -> int:
        return self.records.call(
            context,
            self.spec,
            scope_for(self.spec, context.spec) or "none",
            args_sha,
            outcome,
            reason,
            max(0, int((self.now() - started) * 1000)),
        )

    def refused(self, context: ToolContext, reason: str) -> None:
        """The tool gate refused the call; it still leaves a record (FR-004)."""
        self._record(context, sha256_of({}), "refused", reason or "not permitted", self.now())

    def call(self, arguments: Mapping[str, Any], context: ToolContext) -> str:
        started = self.now()
        allowed = {k: v for k, v in arguments.items() if k in self.spec.model_args()}
        args_sha = sha256_of(allowed)
        scope = scope_for(self.spec, context.spec)
        if scope is None:
            reason = "refused: this terminal has no single environment scope"
            self._record(context, args_sha, "refused", reason, started)
            return f"{self.name} {reason}"
        bound = self.bound.resolve(self.spec, scope, context)
        missing = sorted(name for name, value in bound.items() if not value)
        if missing:
            reason = f"refused: no {', '.join(m.replace('_', ' ') for m in missing)} for this run"
            self._record(context, args_sha, "refused", reason, started)
            return f"{self.name} {reason}"
        token = sign(
            issue(
                run_id=context.run_id,
                usecase_id=context.usecase_id,
                terminal_id=context.terminal_id,
                attempt=context.attempt,
                scopes=mcp_scopes(context.spec),
                bound={k: v for k, v in bound.items() if v},
                now=self.now(),
            ),
            self.key,
        )
        try:
            failed, text = self.client(self.host, self.spec.server, self.spec.name, allowed, token)
        except ToolUnavailable:
            reason = f"unavailable: the {self.spec.server} server did not answer"
            self._record(context, args_sha, "unavailable", reason, started)
            return f"{self.name} {reason}"
        if failed:
            outcome = _outcome(text)
            self._record(context, args_sha, outcome, text[:2000] or outcome, started)
            return f"{self.name} {outcome}: {text}"
        call_id = self._record(context, args_sha, "ok", "", started)
        if self.spec.evidence is not None:
            result = _json(text)
            package = _package(result)
            result_id = self.records.result(call_id, context, self.spec.evidence, package, result)
            if isinstance(result, dict):  # 011: the agent can cite or import this result
                view = agent_view(result)
                return json.dumps({"result_id": result_id, **view}, ensure_ascii=False)
        return text


LONG_LIST = 20  # rows of a list the agent sees in full; longer ones are stored, not shown


def agent_view(result: Mapping[str, Any]) -> dict[str, Any]:
    """011: what the model sees of an evidence result. The full result is recorded; long lists
    (per-case rows, findings) are replaced by their size, to import or read by ``result_id``,
    so the metrics the agent must copy are never cut off."""
    view: dict[str, Any] = {}
    for key, value in result.items():
        if isinstance(value, list) and len(value) > LONG_LIST:
            view[key] = {"count": len(value), "stored": "import or cite it by result_id"}
        else:
            view[key] = value
    return view


def _json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"text": text}


def _package(result: Any) -> str | None:
    if isinstance(result, Mapping):
        value = str(result.get("package_hash") or "")
        if value.startswith(SHA) and len(value) == len(SHA) + 64:
            return value
    return None


# ------------------------------------------------------------------ building the tools


def mcp_tools(
    agents: AgentCatalogue,
    registry: Registry,
    client: McpClientLike,
    key: str,
    bound: BoundValues,
    records: ToolRecords,
    *,
    catalogue: Catalogue = CATALOGUE,
    hosts: Sequence[str] = TOOL_HOSTS,
) -> dict[str, Tool]:
    """A tool for every agent binding ``<server>_<tool>`` with permission ``mcp:<server>:<scope>``
    whose server is served by a tool host and whose scope fits the catalogued tool."""
    tools: dict[str, Tool] = {}
    for agent in agents.agents.values():
        for binding in agent.tools:
            prefix, _, rest = binding.permission.partition(":")
            server, _, scope = rest.partition(":")
            spec = catalogue.get(binding.tool)
            host = registry.host_of(server)
            if prefix != PERMISSION_PREFIX or spec is None or host not in hosts:
                continue
            if spec.server != server or spec.scope not in (scope, ENVIRONMENT_SCOPE):
                continue
            tools[binding.tool] = McpTool(spec, str(host), client, key, bound, records)
    return tools
