"""The agent runtime behind feature 003's ``AgentRunner`` (006 contracts/runtime.md).

For every build attempt the runner resolves the agent from the catalogue, builds and hashes the
context pack, then either runs the stub (terminal agents until feature 008) or the bounded model
loop. Output is validated in both cases, and every attempt is recorded in ``run.agent_attempt``.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Engine

from adlc.agents.catalogue import AgentCatalogue, AgentDefinition, ModelCatalogue
from adlc.agents.context import (
    ContextPack,
    build_pack,
    builder_messages,
    data_block,
    prerequisite_terminals,
    read_evidence,
    resolve_ceiling,
)
from adlc.agents.gateway import UNAVAILABLE, CallIds, ModelGateway, ModelRequest, request_tokens
from adlc.agents.limits import Budget, Limits, limits_for
from adlc.agents.output import Parsed, correction, parse_builder, validate_artifacts
from adlc.agents.prompts import SpecText, SpecTexts
from adlc.agents.store import insert_attempt
from adlc.agents.telemetry import set_attributes

if TYPE_CHECKING:
    from adlc.agents.knowledge import RetrievalLog
    from adlc.agents.tools import ToolGate
from adlc.config.settings import AgentLimit, AgentLimitOverride
from adlc.ledger.profile import version_values
from adlc.orchestration import spec_view
from adlc.orchestration import store as run_store
from adlc.orchestration.interfaces import (
    AgentResult,
    AgentRunner,
    Artifacts,
    AttemptFailed,
    BudgetExceeded,
    BuildContext,
    Clarification,
    Clock,
    EvalContext,
    ModelUnavailable,
    PolicyEngine,
    Recommendation,
    SystemClock,
)
from adlc.orchestration.tracing import span
from adlc.spec_toolkit.registry import SpecRegistry

MAX_CALL_TOKENS = 16_000  # per call; the gateway also caps at the model's output limit
ToolHandler = Callable[[Mapping[str, Any]], str]


@dataclass
class RuntimeDeps:
    engine: Engine
    registry: SpecRegistry
    models: ModelCatalogue
    agents: AgentCatalogue
    texts: SpecTexts
    gateway: ModelGateway
    policy: PolicyEngine
    limits: Mapping[str, AgentLimit]
    overrides: Mapping[str, AgentLimitOverride] = field(default_factory=dict)
    corrections: int = 2
    clock: Clock = field(default_factory=SystemClock)
    tools: "ToolGate | None" = None  # US4: tool calls are authorized first
    retrievals: "RetrievalLog | None" = None  # 008: knowledge results, for citation checks


@dataclass
class LoopOutcome:
    result: (
        Artifacts
        | Clarification
        | Recommendation
        | AttemptFailed
        | BudgetExceeded
        | ModelUnavailable
    )
    steps: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: Decimal | None = Decimal(0)
    corrections: int = 0
    limit_reached: str | None = None


def run_loop(
    deps: RuntimeDeps,
    *,
    tier: str,
    data_class: str,
    messages: Sequence[Mapping[str, str]],
    ids: CallIds,
    prompt_hash: str | None,
    context_hash: str,
    limits: Limits,
    parse: Callable[[str], Parsed],
    on_tool: ToolHandler | None = None,
) -> LoopOutcome:
    """The bounded model loop shared by builder agents and the reviewer."""
    budget = Budget(limits)
    conversation = [dict(m) for m in messages]
    out = LoopOutcome(result=AttemptFailed("no answer"))

    def finish(result: Any, limit: str | None = None) -> LoopOutcome:
        out.result, out.limit_reached = result, limit
        out.steps = budget.steps
        return out

    if request_tokens(conversation) > limits.tokens:
        return finish(BudgetExceeded("tokens"), "tokens")
    while True:
        limit = budget.exceeded()
        if limit is not None:
            return finish(BudgetExceeded(limit), limit)
        response = deps.gateway.complete(
            ModelRequest(
                tier=tier,
                data_class=data_class,
                messages=tuple(conversation),
                max_tokens=max(1, min(budget.remaining_tokens(), MAX_CALL_TOKENS)),
                timeout_s=budget.remaining_s(),
                ids=ids,
                prompt_hash=prompt_hash,
                context_hash=context_hash,
            )
        )
        budget.spend(response.tokens_in, response.tokens_out)
        out.tokens_in += response.tokens_in
        out.tokens_out += response.tokens_out
        out.cost_usd = (
            None
            if out.cost_usd is None or response.cost_usd is None
            else out.cost_usd + response.cost_usd
        )
        if response.outcome == UNAVAILABLE:
            return finish(ModelUnavailable(response.reason or "no model available"))
        if response.outcome != "ok":
            if out.corrections >= deps.corrections:
                return finish(AttemptFailed(f"{response.outcome}: {response.reason or ''}".strip()))
            out.corrections += 1
            conversation.append(
                {
                    "role": "user",
                    "content": f"Your previous answer could not be used ({response.outcome}). "
                    "Answer again with one JSON object as required.",
                }
            )
            continue
        parsed = parse(response.text)
        conversation.append({"role": "assistant", "content": response.text})
        if parsed.tool is not None:
            if on_tool is None:
                conversation.append({"role": "user", "content": "No tools are available to you."})
            else:
                conversation.append({"role": "user", "content": on_tool(parsed.tool)})
            continue
        if parsed.problems:
            if out.corrections >= deps.corrections:
                return finish(AttemptFailed("; ".join(parsed.problems)))
            out.corrections += 1
            conversation.append({"role": "user", "content": correction(parsed.problems)})
            continue
        return finish(parsed.result)


def outcome_name(result: Any) -> str:
    return {
        Artifacts: "artifacts",
        Clarification: "clarification",
        Recommendation: "recommendation",
        BudgetExceeded: "budget_exceeded",
        AttemptFailed: "failed",
        ModelUnavailable: "model_unavailable",
    }[type(result)]


def failure_reason(result: Any) -> str | None:
    if isinstance(result, AttemptFailed):
        return result.reason
    if isinstance(result, BudgetExceeded | ModelUnavailable):
        return result.detail
    return None


def record_attempt(
    deps: RuntimeDeps,
    *,
    run_id: str,
    kind: str,
    attempt: int,
    agent: AgentDefinition,
    prompt: SpecText | None,
    pack: ContextPack,
    outcome: LoopOutcome,
    started_at: datetime,
) -> None:
    insert_attempt(
        deps.engine,
        {
            "run_id": run_id,
            "kind": kind,
            "attempt": attempt,
            "agent_id": agent.id,
            "agent_version": agent.version,
            "implementation": agent.implementation,
            "prompt_hash": None
            if prompt is None or agent.implementation == "stub"
            else prompt.hash,
            "playbook_hashes": dict(pack.playbook_hashes),
            "context_hash": pack.hash,
            "steps": outcome.steps,
            "tokens_in": outcome.tokens_in,
            "tokens_out": outcome.tokens_out,
            "cost_usd": outcome.cost_usd,
            "corrections": outcome.corrections,
            "outcome": outcome_name(outcome.result),
            "limit_reached": outcome.limit_reached,
            "reason": failure_reason(outcome.result),
            "started_at": started_at,
            "ended_at": deps.clock.now(),
        },
    )


def data_ceiling(spec: Mapping[str, Any]) -> str:
    access = (spec_view.body(spec).get("authorities") or {}).get("data_access") or {}
    return str(access.get("max_class") or "")


def _data_classes(deps: RuntimeDeps) -> Mapping[str, Any]:
    entry = deps.registry.catalogue("data_classes")
    return {} if entry is None else entry.content


def playbook_texts(texts: SpecTexts, spec: Mapping[str, Any]) -> list[SpecText]:
    procedures = (spec_view.body(spec).get("playbooks") or {}).get("procedures") or []
    return [texts.playbook(str(p["id"]), str(p["version"])) for p in procedures]


class RuntimeAgentRunner:
    """``AgentRunner`` for every terminal agent (stub or model)."""

    def __init__(self, deps: RuntimeDeps, stub: AgentRunner) -> None:
        self.deps = deps
        self.stub = stub

    def build(self, context: BuildContext) -> AgentResult:
        deps = self.deps
        spec = context.spec
        agent = deps.agents.agent(
            str((spec_view.body(spec).get("actors") or {}).get("agent", {}).get("id"))
        )
        usecase_id = str(context.usecase.get("usecase_id"))
        with deps.engine.connect() as conn:
            run = run_store.load_run(conn, context.run_id)
            profile_version = 0 if run is None else run.profile_version
            spec_version = "" if run is None else run.spec_version
            profile = version_values(conn, usecase_id, profile_version)
            evidence = read_evidence(conn, usecase_id, prerequisite_terminals(spec))
            ceiling = resolve_ceiling(conn, usecase_id, data_ceiling(spec), _data_classes(deps))
        entry = deps.registry.entry(context.terminal_id, spec_version or None)
        prompt = (
            deps.texts.prompt(*agent.prompt)
            if agent.implementation == "model" and agent.prompt
            else None
        )
        pack = build_pack(
            agent=agent,
            prompt=prompt,
            spec=spec,
            spec_version=spec_version,
            spec_hash="" if entry is None else entry.content_hash,
            usecase=context.usecase,
            profile_version=profile_version,
            profile_values=profile,
            evidence=evidence,
            trigger=context.trigger,
            clarifications=context.clarifications,
            failed_controls=context.failed_controls,
            previous_artifacts=context.previous_artifacts,
            playbooks=playbook_texts(deps.texts, spec),
        )
        required = self._required(context, usecase_id)
        started = deps.clock.now()
        ids = {
            "run_id": context.run_id,
            "usecase_id": usecase_id,
            "terminal_id": context.terminal_id,
        }
        with span("agent", "attempt", **ids) as s:
            if agent.implementation == "stub":
                outcome = LoopOutcome(result=self._stub(context, spec, required))
            else:
                if prompt is None:
                    raise ValueError(f"model agent {agent.id} has no prompt")
                limits = limits_for(
                    deps.limits, deps.overrides, agent.model_tier, context.terminal_id
                )
                handler = (
                    None
                    if deps.tools is None or not agent.tools
                    else deps.tools.handler(
                        context.run_id,
                        usecase_id,
                        context.terminal_id,
                        agent,
                        spec=spec,
                        attempt=context.attempt,
                    )
                )
                tools = [] if deps.tools is None else deps.tools.describe(agent)
                roles = {r.role for r in spec_view.human_roles(spec)}
                log = deps.retrievals

                def retrieved() -> list[Any]:
                    return [] if log is None else log.for_attempt(context.run_id, context.attempt)

                outcome = run_loop(
                    deps,
                    tier=agent.model_tier,
                    data_class=ceiling,
                    messages=builder_messages(
                        pack,
                        prompt,
                        spec,
                        [a.id for a in spec_view.artifacts(spec) if required(a)],
                        tools,
                    ),
                    ids=CallIds(
                        context.run_id,
                        usecase_id,
                        context.terminal_id,
                        agent.id,
                        f"{context.run_id}/build/{context.attempt}",
                    ),
                    prompt_hash=prompt.hash,
                    context_hash=pack.hash,
                    limits=limits,
                    parse=lambda raw: parse_builder(raw, spec, required, roles, retrieved),
                    on_tool=handler,
                )
            set_attributes(
                s,
                {
                    "kind": "build",
                    "agent_id": agent.id,
                    "agent_version": agent.version,
                    "implementation": agent.implementation,
                    "attempt": context.attempt,
                    "outcome": outcome_name(outcome.result),
                    "steps": outcome.steps,
                    "tokens_in": outcome.tokens_in,
                    "tokens_out": outcome.tokens_out,
                    "corrections": outcome.corrections,
                    "limit_reached": outcome.limit_reached,
                },
            )
        record_attempt(
            deps,
            run_id=context.run_id,
            kind="build",
            attempt=context.attempt,
            agent=agent,
            prompt=prompt,
            pack=pack,
            outcome=outcome,
            started_at=started,
        )
        return outcome.result  # type: ignore[return-value]

    def _stub(
        self, context: BuildContext, spec: Mapping[str, Any], required: Callable[[Any], bool]
    ) -> AgentResult:
        result = self.stub.build(context)
        if isinstance(result, Artifacts):
            problems = validate_artifacts(result.artifacts, spec, required)
            if problems:
                return AttemptFailed("; ".join(problems))
        return result

    def _required(
        self, context: BuildContext, usecase_id: str
    ) -> Callable[[spec_view.ArtifactSpec], bool]:
        """Mandatory artifacts always; a conditional one when its condition holds (policy)."""

        def required(artifact: spec_view.ArtifactSpec) -> bool:
            if artifact.condition is None:
                return True
            result = self.deps.policy.evaluate(
                artifact.condition,
                EvalContext(
                    context.terminal_id, f"applicability:{artifact.id}", context.run_id, usecase_id
                ),
            )
            return result.passed

        return required


def tool_result_block(tool: str, text: str) -> str:
    return data_block(f"tool:{tool}", text)
