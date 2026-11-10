"""Boundaries of the orchestrator (contracts/interfaces.md; constitution VII).

Features 004 (policy engine) and 006 (agent runtime and reviewer) replace the stubs in
:mod:`adlc.orchestration.stubs` by implementing these protocols.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

Rows = list[dict[str, Any]]
ArtifactSet = dict[str, Rows]


# ------------------------------------------------------------------ policy


@dataclass(frozen=True)
class EvalContext:
    """What a policy evaluation is about. ``check_id`` names the prerequisite, control,
    condition or route being evaluated, so a policy (or a test script) can address it."""

    terminal_id: str
    check_id: str
    run_id: str | None = None
    usecase_id: str | None = None
    variables: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalResult:
    passed: bool
    value: Any = None
    reason: str = ""


class PolicyEngine(Protocol):
    def evaluate(self, expression: str, context: EvalContext) -> EvalResult: ...

    def authorize(self, actor: str, action: str, resource: str, context: EvalContext) -> bool: ...


# ------------------------------------------------------------------ agent and reviewer


@dataclass(frozen=True)
class Artifacts:
    artifacts: ArtifactSet


@dataclass(frozen=True)
class Clarification:
    questions: tuple[str, ...]
    addressed_role: str | None = None
    looked_in: tuple[str, ...] = ()


@dataclass(frozen=True)
class BudgetExceeded:
    detail: str = ""


AgentResult = Artifacts | Clarification | BudgetExceeded


@dataclass(frozen=True)
class Recommendation:
    status: str
    checklist_scores: Mapping[str, int] = field(default_factory=dict)
    findings: tuple[str, ...] = ()


ReviewResult = Recommendation | Clarification


@dataclass(frozen=True)
class BuildContext:
    """What the agent receives (SA §7.2); the full context builder arrives in 006."""

    run_id: str
    terminal_id: str
    spec: Mapping[str, Any]
    usecase: Mapping[str, Any]
    trigger: Mapping[str, Any]
    previous_artifacts: ArtifactSet
    clarifications: tuple[Mapping[str, Any], ...]
    attempt: int
    failed_controls: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class ReviewContext:
    """What the reviewer receives: never the builder's reasoning (SA §7.2 point 5)."""

    run_id: str
    terminal_id: str
    checklist_items: tuple[str, ...]
    artifacts: ArtifactSet
    control_results: tuple[Mapping[str, Any], ...]
    clarifications: tuple[Mapping[str, Any], ...] = ()


class AgentRunner(Protocol):
    def build(self, context: BuildContext) -> AgentResult: ...


class Reviewer(Protocol):
    def review(self, context: ReviewContext) -> ReviewResult: ...


# ------------------------------------------------------------------ time


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)
