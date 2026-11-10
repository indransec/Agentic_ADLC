"""The terminal-run state machine (contracts/state-machine.md; SA §6.2; constitution III).

``transition`` is a pure function: given a state, a signal and the run's counters, it returns
the next state and a tuple of effects, or raises ``InvalidTransition``. The engine executes the
effects in the same database transaction. Outcome rights are part of the table: decisions come
only from humans, escalation only from the orchestrator.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RunState(StrEnum):
    OPENED = "opened"
    BLOCKED = "blocked"
    BUILDING = "building"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    CHECKING = "checking"
    REVIEWING = "reviewing"
    AWAITING_SIGN_OFF = "awaiting_sign_off"
    ESCALATED = "escalated"
    CLOSED = "closed"


AUTOMATIC = frozenset({RunState.OPENED, RunState.BUILDING, RunState.CHECKING, RunState.REVIEWING})
WAITING = frozenset(
    {
        RunState.BLOCKED,
        RunState.AWAITING_CLARIFICATION,
        RunState.AWAITING_SIGN_OFF,
        RunState.ESCALATED,
    }
)
OPEN = AUTOMATIC | WAITING


class ActorType(StrEnum):
    HUMAN = "human"
    AGENT = "agent"
    REVIEWER = "reviewer"
    ORCHESTRATOR = "orchestrator"
    SYSTEM = "system"


class SignalKind(StrEnum):
    PREREQUISITES_RESULT = "prerequisites_result"
    EVENT_RECEIVED = "event_received"
    AGENT_RESULT = "agent_result"
    CONTROLS_RESULT = "controls_result"
    REVIEW_RESULT = "review_result"
    CLARIFICATION_ANSWERED = "clarification_answered"
    DECIDE = "decide"
    WAIVER_DECISION = "waiver_decision"
    ESCALATION_COMPLETED = "escalation_completed"
    TIMER = "timer"
    OPEN_ESCALATED = "open_escalated"
    STEP_INTERRUPTED = "step_interrupted"
    LIFECYCLE_ENDED = "lifecycle_ended"
    ARTIFACT_EDITED = "artifact_edited"  # 005: a person edited an artifact
    CONTROLS_RECHECKED = "controls_rechecked"  # 005: controls re-run on edited content


ALLOWED_ACTOR: Mapping[SignalKind, ActorType] = {
    SignalKind.PREREQUISITES_RESULT: ActorType.ORCHESTRATOR,
    SignalKind.EVENT_RECEIVED: ActorType.ORCHESTRATOR,
    SignalKind.AGENT_RESULT: ActorType.AGENT,
    SignalKind.CONTROLS_RESULT: ActorType.ORCHESTRATOR,
    SignalKind.REVIEW_RESULT: ActorType.REVIEWER,
    SignalKind.CLARIFICATION_ANSWERED: ActorType.HUMAN,
    SignalKind.DECIDE: ActorType.HUMAN,
    SignalKind.WAIVER_DECISION: ActorType.HUMAN,
    SignalKind.ESCALATION_COMPLETED: ActorType.HUMAN,
    SignalKind.TIMER: ActorType.ORCHESTRATOR,
    SignalKind.OPEN_ESCALATED: ActorType.ORCHESTRATOR,
    SignalKind.STEP_INTERRUPTED: ActorType.ORCHESTRATOR,
    # A terminate decision (or a terminating route) ends the other runs of the use case;
    # the deciding person is the actor (FR-018c).
    SignalKind.LIFECYCLE_ENDED: ActorType.HUMAN,
    SignalKind.ARTIFACT_EDITED: ActorType.HUMAN,
    SignalKind.CONTROLS_RECHECKED: ActorType.ORCHESTRATOR,
}

DECISIONS = frozenset({"pass", "rework", "exception", "terminate"})
TIMER_KINDS = frozenset({"escalate_after", "clarification_sla"})


@dataclass(frozen=True)
class Signal:
    kind: SignalKind
    actor_type: ActorType
    actor_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TransitionContext:
    """Limits from the pinned spec and the run's counters at the time of the signal."""

    max_clarification_rounds: int = 2
    max_auto_retries: int = 3
    clarification_rounds: int = 0
    auto_retries: int = 0
    return_state: RunState | None = None
    pending_waiver: bool = False
    min_approvers: int = 1
    rule_roles: frozenset[str] = frozenset()
    required_plus_roles: frozenset[str] = frozenset()
    approvals: tuple[tuple[str, str], ...] = ()  # (person, role) of pass sign-offs so far
    controls_pending: bool = False  # 005: an edit's controls have not been re-run yet


# ------------------------------------------------------------------ effects


@dataclass(frozen=True)
class StartTimer:
    kind: str


@dataclass(frozen=True)
class CancelTimer:
    kind: str


@dataclass(frozen=True)
class CancelAllTimers:
    pass


@dataclass(frozen=True)
class Escalate:
    trigger: str


@dataclass(frozen=True)
class CloseRun:
    status: str


@dataclass(frozen=True)
class RecordSignOff:
    decision: str


@dataclass(frozen=True)
class ProposeWaiver:
    pass


@dataclass(frozen=True)
class DecideWaiver:
    approve: bool


@dataclass(frozen=True)
class RecordClarification:
    asked_by: str


@dataclass(frozen=True)
class SetReturnState:
    state: RunState | None


@dataclass(frozen=True)
class IncrementAutoRetry:
    pass


@dataclass(frozen=True)
class StoreArtifacts:
    pass


@dataclass(frozen=True)
class StoreControls:
    pass


@dataclass(frozen=True)
class StoreRecommendation:
    pass


@dataclass(frozen=True)
class RecordEvent:
    pass


@dataclass(frozen=True)
class ClearApprovals:
    """005: approvals given before an artifact edit no longer count."""


@dataclass(frozen=True)
class SetControlsPending:
    """005: after an edit at sign-off, nobody can pass until the controls are re-run."""

    pending: bool


@dataclass(frozen=True)
class WithdrawWaiver:
    """005: an edit while a waiver is pending withdraws it (the approvers decide again)."""


Effect = (
    StartTimer
    | CancelTimer
    | CancelAllTimers
    | Escalate
    | CloseRun
    | RecordSignOff
    | ProposeWaiver
    | DecideWaiver
    | RecordClarification
    | SetReturnState
    | IncrementAutoRetry
    | StoreArtifacts
    | StoreControls
    | StoreRecommendation
    | RecordEvent
    | WithdrawWaiver
    | ClearApprovals
    | SetControlsPending
)


@dataclass(frozen=True)
class Outcome:
    next_state: RunState
    effects: tuple[Effect, ...] = ()


class InvalidTransition(Exception):
    """The signal is not allowed in this state, from this actor, or with this payload."""


# ------------------------------------------------------------------ the table


def transition(state: RunState, signal: Signal, ctx: TransitionContext) -> Outcome:
    if signal.actor_type != ALLOWED_ACTOR[signal.kind]:
        raise InvalidTransition(
            f"actor {signal.actor_type} may not send {signal.kind} "
            f"(only {ALLOWED_ACTOR[signal.kind]})"
        )
    if state == RunState.CLOSED:
        raise InvalidTransition(f"run is closed; {signal.kind} refused")
    outcome = _transition(state, signal, ctx)
    if outcome is None:
        raise InvalidTransition(f"{signal.kind} is not allowed in state {state}")
    return outcome


def _transition(state: RunState, signal: Signal, ctx: TransitionContext) -> Outcome | None:
    kind, p = signal.kind, signal.payload

    if kind == SignalKind.LIFECYCLE_ENDED:
        return Outcome(RunState.CLOSED, (CancelAllTimers(), CloseRun("terminate")))
    if kind == SignalKind.TIMER:
        return _timer(state, str(p.get("kind")))
    if kind == SignalKind.EVENT_RECEIVED:
        return Outcome(RunState.OPENED if state == RunState.BLOCKED else state, (RecordEvent(),))
    if kind == SignalKind.STEP_INTERRUPTED:
        if state not in AUTOMATIC:
            return None
        if ctx.auto_retries >= ctx.max_auto_retries:
            return Outcome(RunState.ESCALATED, (Escalate("retry_limit"),))
        return Outcome(state, (IncrementAutoRetry(),))
    if kind == SignalKind.DECIDE:
        return _decide(state, signal, ctx)
    handler = _HANDLERS.get((state, kind))
    return None if handler is None else handler(p, ctx)


def _timer(state: RunState, kind: str) -> Outcome | None:
    if kind == "escalate_after":
        if state == RunState.ESCALATED:
            return Outcome(state)  # an escalated run does not escalate again (FR-021)
        return Outcome(RunState.ESCALATED, (Escalate("timer"),))
    if kind == "clarification_sla" and state == RunState.AWAITING_CLARIFICATION:
        return Outcome(RunState.ESCALATED, (Escalate("clarification_sla"),))
    return None


def _clarification(asked_by: str, back_to: RunState, ctx: TransitionContext) -> Outcome:
    if ctx.clarification_rounds >= ctx.max_clarification_rounds:
        return Outcome(RunState.ESCALATED, (Escalate("clarification_limit"),))
    return Outcome(
        RunState.AWAITING_CLARIFICATION,
        (RecordClarification(asked_by), SetReturnState(back_to), StartTimer("clarification_sla")),
    )


def _open_escalated(p: Mapping[str, Any], ctx: TransitionContext) -> Outcome:
    return Outcome(RunState.ESCALATED, (Escalate(str(p.get("trigger", "rework_limit"))),))


def _prerequisites(p: Mapping[str, Any], ctx: TransitionContext) -> Outcome:
    return Outcome(RunState.BUILDING if p.get("met") else RunState.BLOCKED)


def _agent(p: Mapping[str, Any], ctx: TransitionContext) -> Outcome | None:
    result = p.get("result")
    if result == "artifacts":
        return Outcome(RunState.CHECKING, (StoreArtifacts(),))
    if result == "clarification":
        return _clarification("agent", RunState.BUILDING, ctx)
    if result == "budget_exceeded":
        return Outcome(RunState.ESCALATED, (Escalate("budget"),))
    if result == "failed":  # 006: output still unfit after corrections, or a refusal
        if ctx.auto_retries >= ctx.max_auto_retries:
            return Outcome(RunState.ESCALATED, (Escalate("retry_limit"),))
        return Outcome(RunState.BUILDING, (IncrementAutoRetry(),))
    if result == "model_unavailable":  # 006: sent only after the outage limit
        return Outcome(RunState.ESCALATED, (Escalate("model_unavailable"),))
    return None


def _controls(p: Mapping[str, Any], ctx: TransitionContext) -> Outcome:
    if p.get("passed"):
        return Outcome(RunState.REVIEWING, (StoreControls(),))
    if ctx.auto_retries >= ctx.max_auto_retries:
        return Outcome(RunState.ESCALATED, (StoreControls(), Escalate("retry_limit")))
    return Outcome(RunState.BUILDING, (StoreControls(), IncrementAutoRetry()))


def _review(p: Mapping[str, Any], ctx: TransitionContext) -> Outcome | None:
    result = p.get("result")
    if result == "recommendation":
        return Outcome(RunState.AWAITING_SIGN_OFF, (StoreRecommendation(),))
    if result == "clarification":
        return _clarification("reviewer", RunState.REVIEWING, ctx)
    if result == "failed":  # 006: the reviewer's output never fit
        return Outcome(RunState.ESCALATED, (Escalate("reviewer_failed"),))
    if result == "model_unavailable":
        return Outcome(RunState.ESCALATED, (Escalate("model_unavailable"),))
    return None


def _answered(p: Mapping[str, Any], ctx: TransitionContext) -> Outcome | None:
    if ctx.return_state not in (RunState.BUILDING, RunState.REVIEWING):
        return None
    return Outcome(ctx.return_state, (CancelTimer("clarification_sla"), SetReturnState(None)))


def _waiver(p: Mapping[str, Any], ctx: TransitionContext) -> Outcome | None:
    if not ctx.pending_waiver:
        return None
    if p.get("approve") is True:
        return Outcome(RunState.CLOSED, (DecideWaiver(approve=True), CloseRun("exception")))
    return Outcome(RunState.AWAITING_SIGN_OFF, (DecideWaiver(approve=False),))


def _completed(p: Mapping[str, Any], ctx: TransitionContext) -> Outcome:
    return Outcome(RunState.AWAITING_SIGN_OFF, (StoreArtifacts(),))


def _edited(state: RunState) -> Callable[[Mapping[str, Any], TransitionContext], Outcome]:
    """Stores the person's version; approvals given before it no longer count; a pending waiver
    is withdrawn. The state is unchanged."""

    def handle(p: Mapping[str, Any], ctx: TransitionContext) -> Outcome:
        effects: tuple[Effect, ...] = (StoreArtifacts(), ClearApprovals())
        if ctx.pending_waiver:
            effects += (WithdrawWaiver(),)
        if state == RunState.AWAITING_SIGN_OFF:
            effects += (SetControlsPending(True),)
        return Outcome(state, effects)

    return handle


def _rechecked(state: RunState) -> Callable[[Mapping[str, Any], TransitionContext], Outcome]:
    def handle(p: Mapping[str, Any], ctx: TransitionContext) -> Outcome:
        return Outcome(state, (StoreControls(), SetControlsPending(False)))

    return handle


_HANDLERS = {
    (RunState.OPENED, SignalKind.OPEN_ESCALATED): _open_escalated,
    (RunState.OPENED, SignalKind.PREREQUISITES_RESULT): _prerequisites,
    (RunState.BUILDING, SignalKind.AGENT_RESULT): _agent,
    (RunState.CHECKING, SignalKind.CONTROLS_RESULT): _controls,
    (RunState.REVIEWING, SignalKind.REVIEW_RESULT): _review,
    (RunState.AWAITING_CLARIFICATION, SignalKind.CLARIFICATION_ANSWERED): _answered,
    (RunState.AWAITING_SIGN_OFF, SignalKind.WAIVER_DECISION): _waiver,
    (RunState.ESCALATED, SignalKind.ESCALATION_COMPLETED): _completed,
    (RunState.AWAITING_SIGN_OFF, SignalKind.ARTIFACT_EDITED): _edited(RunState.AWAITING_SIGN_OFF),
    (RunState.ESCALATED, SignalKind.ARTIFACT_EDITED): _edited(RunState.ESCALATED),
    (RunState.AWAITING_SIGN_OFF, SignalKind.CONTROLS_RECHECKED): _rechecked(
        RunState.AWAITING_SIGN_OFF
    ),
    (RunState.ESCALATED, SignalKind.CONTROLS_RECHECKED): _rechecked(RunState.ESCALATED),
}


def sign_off_complete(ctx: TransitionContext, approvals: tuple[tuple[str, str], ...]) -> bool:
    """``min_approvers`` distinct rule approvers, plus every required ``plus`` role (FR-009b)."""
    rule_people = {person for person, role in approvals if role in ctx.rule_roles}
    plus_roles = {role for _, role in approvals if role in ctx.required_plus_roles}
    return len(rule_people) >= ctx.min_approvers and ctx.required_plus_roles <= plus_roles


def _decide(state: RunState, signal: Signal, ctx: TransitionContext) -> Outcome | None:
    decision = signal.payload.get("decision")
    if decision not in DECISIONS:
        return None
    if decision == "terminate":
        if state not in (RunState.BLOCKED, RunState.ESCALATED, RunState.AWAITING_SIGN_OFF):
            return None
        return Outcome(RunState.CLOSED, (RecordSignOff("terminate"), CloseRun("terminate")))
    if state != RunState.AWAITING_SIGN_OFF or ctx.pending_waiver:
        return None
    if decision == "rework":
        return Outcome(RunState.CLOSED, (RecordSignOff("rework"), CloseRun("rework")))
    if ctx.controls_pending:  # 005 FR-010: decide on checked content only
        raise InvalidTransition("controls are being re-run after an edit; decide once they finish")
    if decision == "exception":
        return Outcome(RunState.AWAITING_SIGN_OFF, (RecordSignOff("exception"), ProposeWaiver()))
    role = str(signal.payload.get("role"))
    if role not in ctx.rule_roles | ctx.required_plus_roles:
        raise InvalidTransition(f"role {role} cannot sign off this run")
    if any(person == signal.actor_id for person, _ in ctx.approvals):
        return Outcome(state)  # the same person passing twice counts once
    approvals = (*ctx.approvals, (signal.actor_id, role))
    if sign_off_complete(ctx, approvals):
        return Outcome(RunState.CLOSED, (RecordSignOff("pass"), CloseRun("pass")))
    return Outcome(RunState.AWAITING_SIGN_OFF, (RecordSignOff("pass"),))
