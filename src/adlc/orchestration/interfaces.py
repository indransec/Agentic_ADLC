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
    attempt: int | None = None  # 005: the build attempt a control is checked for


@dataclass(frozen=True)
class EvalResult:
    passed: bool
    value: Any = None
    reason: str = ""
    synthetic: bool = False  # 004: true when any input came from the synthetic provider


class PolicyEngine(Protocol):
    def evaluate(self, expression: str, context: EvalContext) -> EvalResult: ...

    def authorize(self, actor: str, action: str, resource: str, context: EvalContext) -> bool: ...


# ------------------------------------------------------------------ agent and reviewer


@dataclass(frozen=True)
class Artifacts:
    artifacts: ArtifactSet
    citations: tuple["Citation", ...] = ()  # 008: validated against the attempt's retrievals


@dataclass(frozen=True)
class Citation:
    """A knowledge passage an artifact (or one of its rows) relies on (008 FR-015). The hash and
    retrieval id come from the retrieval record, never from the model."""

    artifact: str
    row: int | None
    source: str
    document: str
    section: str
    content_hash: str
    retrieval_id: int


@dataclass(frozen=True)
class Clarification:
    questions: tuple[str, ...]
    addressed_role: str | None = None
    looked_in: tuple[str, ...] = ()


@dataclass(frozen=True)
class BudgetExceeded:
    detail: str = ""  # 006: names the limit reached: tokens, steps or timeout


@dataclass(frozen=True)
class AttemptFailed:
    """006: output still unfit after the corrections, a refusal, or a request that cannot work.
    Counted as a failed build attempt, or escalates a review (``reviewer_failed``)."""

    reason: str = ""


@dataclass(frozen=True)
class ModelUnavailable:
    """006: no model of the tier could run (keys, outages). The engine defers the run, and
    escalates it once the outage limit has passed."""

    detail: str = ""


AgentResult = Artifacts | Clarification | BudgetExceeded | AttemptFailed | ModelUnavailable


@dataclass(frozen=True)
class Recommendation:
    status: str
    checklist_scores: Mapping[str, int] = field(default_factory=dict)
    findings: tuple[str, ...] = ()
    reason: str = ""  # 006: the reviewer's reason for the recommended status
    root_cause: str | None = None  # 006: required with rework, from the root-cause catalogue
    reviewer: str = "stub"  # 006: stub or model


ReviewResult = Recommendation | Clarification | AttemptFailed | ModelUnavailable


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
