"""The tool gate: every tool or data access an agent asks for is authorized first (006 FR-020).

The action and resource come from the tool binding's declared permission in the agents catalogue
(``action:resource``, e.g. ``read:knowledge_base`` or ``mcp:jira:read``). Authorization is
feature 004's ``authorize``, run-scoped (``agent:<run id>``). A refused call is not made; the
refusal and its reason go back to the agent. Output is wrapped as a data block.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from adlc.agents.catalogue import AgentDefinition
from adlc.agents.context import data_block
from adlc.orchestration.interfaces import EvalContext, PolicyEngine
from adlc.orchestration.tracing import span

MAX_OUTPUT = 20_000  # characters of tool output passed to the model


class Tool(Protocol):
    def call(self, arguments: Mapping[str, Any]) -> str: ...


@dataclass(frozen=True)
class ToolOutput:
    text: str


@dataclass(frozen=True)
class ToolRefused:
    reason: str


@dataclass
class FakeTool:
    """A tool for tests: returns a fixed text and records its calls."""

    text: str = "tool output"
    calls: list[Mapping[str, Any]] = field(default_factory=list)

    def call(self, arguments: Mapping[str, Any]) -> str:
        self.calls.append(dict(arguments))
        return self.text


class ToolGate:
    def __init__(self, policy: PolicyEngine, tools: Mapping[str, Tool]) -> None:
        self.policy = policy
        self.tools = dict(tools)

    def call(
        self,
        *,
        run_id: str,
        usecase_id: str,
        terminal_id: str,
        agent: AgentDefinition,
        name: str,
        arguments: Mapping[str, Any],
        on_behalf_of: str | None = None,
    ) -> ToolOutput | ToolRefused:
        """``on_behalf_of`` names the run the call is for; an agent may act only for its own."""
        binding = agent.tool(name)
        if binding is None or name not in self.tools:
            return ToolRefused(f"tool {name} is not available to {agent.id}")
        context = EvalContext(terminal_id, f"tool:{name}", on_behalf_of or run_id, usecase_id)
        actor = f"agent:{run_id}"
        with span("agent", "tool", run_id=run_id, usecase_id=usecase_id, terminal_id=terminal_id):
            decide = getattr(self.policy, "authorize_decision", None)
            if decide is not None:
                allowed, reason = decide(actor, binding.action, binding.resource, context)
            else:
                allowed = self.policy.authorize(actor, binding.action, binding.resource, context)
                reason = "" if allowed else f"not permitted: {binding.permission}"
            if not allowed:
                return ToolRefused(str(reason) or f"not permitted: {binding.permission}")
            return ToolOutput(self.tools[name].call(arguments)[:MAX_OUTPUT])

    def handler(
        self, run_id: str, usecase_id: str, terminal_id: str, agent: AgentDefinition
    ) -> Any:
        """The loop's tool hook: returns the next user message (data or refusal)."""

        def handle(request: Mapping[str, Any]) -> str:
            name = str(request.get("name"))
            result = self.call(
                run_id=run_id,
                usecase_id=usecase_id,
                terminal_id=terminal_id,
                agent=agent,
                name=name,
                arguments=dict(request.get("arguments") or {}),
            )
            if isinstance(result, ToolRefused):
                return f"Tool {name} was refused: {result.reason}. Continue without it."
            return data_block(f"tool:{name}", result.text)

        return handle
