"""T011: properties of the transition table over arbitrary signal sequences (constitution III)."""

from dataclasses import replace
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from adlc.orchestration.states import (
    ActorType,
    ClearApprovals,
    CloseRun,
    DecideWaiver,
    Effect,
    Escalate,
    IncrementAutoRetry,
    InvalidTransition,
    ProposeWaiver,
    RecordClarification,
    RecordSignOff,
    RunState,
    SetControlsPending,
    SetReturnState,
    Signal,
    SignalKind,
    TransitionContext,
    WithdrawWaiver,
    transition,
)

PAYLOADS: dict[SignalKind, list[dict[str, Any]]] = {
    SignalKind.PREREQUISITES_RESULT: [{"met": True}, {"met": False}],
    SignalKind.EVENT_RECEIVED: [{"event_type": "e"}],
    SignalKind.AGENT_RESULT: [
        {"result": "artifacts"},
        {"result": "clarification"},
        {"result": "budget_exceeded"},
        {"result": "failed"},
        {"result": "model_unavailable"},
    ],
    SignalKind.CONTROLS_RESULT: [{"passed": True}, {"passed": False}],
    SignalKind.REVIEW_RESULT: [
        {"result": "recommendation"},
        {"result": "clarification"},
        {"result": "failed"},
        {"result": "model_unavailable"},
    ],
    SignalKind.CLARIFICATION_ANSWERED: [{}],
    SignalKind.DECIDE: [
        {"decision": d, "role": r}
        for d in ("pass", "rework", "exception", "terminate")
        for r in ("owner", "arch")
    ],
    SignalKind.WAIVER_DECISION: [{"approve": True}, {"approve": False}],
    SignalKind.ESCALATION_COMPLETED: [{}],
    SignalKind.TIMER: [{"kind": "escalate_after"}, {"kind": "clarification_sla"}],
    SignalKind.OPEN_ESCALATED: [{"trigger": "rework_limit"}],
    SignalKind.STEP_INTERRUPTED: [{}],
    SignalKind.LIFECYCLE_ENDED: [{}],
    SignalKind.ARTIFACT_EDITED: [{"artifacts": {}}],
    SignalKind.CONTROLS_RECHECKED: [{"results": []}],
}

signals = st.builds(
    lambda kind, actor, person, index: Signal(
        kind, actor, person, PAYLOADS[kind][index % len(PAYLOADS[kind])]
    ),
    st.sampled_from(list(SignalKind)),
    st.sampled_from(list(ActorType)),
    st.sampled_from(["p1", "p2", "p3"]),
    st.integers(min_value=0, max_value=7),
)
contexts = st.builds(
    TransitionContext,
    max_clarification_rounds=st.integers(0, 3),
    max_auto_retries=st.integers(0, 3),
    min_approvers=st.integers(1, 3),
    rule_roles=st.just(frozenset({"owner"})),
    required_plus_roles=st.sampled_from([frozenset(), frozenset({"arch"})]),
)


def _apply_context(
    ctx: TransitionContext, signal: Signal, effects: tuple[Any, ...]
) -> TransitionContext:
    for effect in effects:
        if isinstance(effect, IncrementAutoRetry):
            ctx = replace(ctx, auto_retries=ctx.auto_retries + 1)
        elif isinstance(effect, RecordClarification):
            ctx = replace(ctx, clarification_rounds=ctx.clarification_rounds + 1)
        elif isinstance(effect, SetReturnState):
            ctx = replace(ctx, return_state=effect.state)
        elif isinstance(effect, ProposeWaiver):
            ctx = replace(ctx, pending_waiver=True)
        elif isinstance(effect, DecideWaiver | WithdrawWaiver):
            ctx = replace(ctx, pending_waiver=False)
        elif isinstance(effect, ClearApprovals):
            ctx = replace(ctx, approvals=())
        elif isinstance(effect, SetControlsPending):
            ctx = replace(ctx, controls_pending=effect.pending)
        elif isinstance(effect, RecordSignOff) and effect.decision == "pass":
            role = str(signal.payload["role"])
            ctx = replace(ctx, approvals=(*ctx.approvals, (signal.actor_id, role)))
    return ctx


def _run(
    ctx: TransitionContext, sequence: list[Signal]
) -> list[tuple[RunState, Signal, tuple[Effect, ...]]]:
    state = RunState.OPENED
    applied = []
    for signal in sequence:
        try:
            out = transition(state, signal, ctx)
        except InvalidTransition:
            continue
        applied.append((out.next_state, signal, out.effects))
        ctx = _apply_context(ctx, signal, out.effects)
        state = out.next_state
    return applied


@settings(max_examples=400, deadline=None)
@given(contexts, st.lists(signals, max_size=40))
def test_no_outcome_without_a_human(ctx: TransitionContext, sequence: list[Signal]) -> None:
    for _, signal, effects in _run(ctx, sequence):
        if any(isinstance(e, CloseRun) for e in effects):
            assert signal.actor_type == ActorType.HUMAN


# Escalation is decided only by the orchestrator's own rules (limits and timers). An agent or
# the reviewer can trigger a rule by what it reports (a clarification over the round limit, a
# budget overrun), never by asking for escalation; humans can never cause it.
RULE_TRIGGERS = {
    ActorType.ORCHESTRATOR: {"timer", "clarification_sla", "retry_limit", "rework_limit"},
    # 006: failed attempts use the retry counter; outages and unfit reviews escalate.
    ActorType.AGENT: {"clarification_limit", "budget", "retry_limit", "model_unavailable"},
    ActorType.REVIEWER: {"clarification_limit", "reviewer_failed", "model_unavailable"},
}


@settings(max_examples=400, deadline=None)
@given(contexts, st.lists(signals, max_size=40))
def test_only_orchestrator_rules_escalate(ctx: TransitionContext, sequence: list[Signal]) -> None:
    previous = RunState.OPENED
    for state, signal, effects in _run(ctx, sequence):
        if state == RunState.ESCALATED and previous != RunState.ESCALATED:
            triggers = [e.trigger for e in effects if isinstance(e, Escalate)]
            assert len(triggers) == 1
            assert triggers[0] in RULE_TRIGGERS.get(signal.actor_type, set()), (signal, triggers)
        previous = state


@settings(max_examples=200, deadline=None)
@given(contexts, st.lists(signals, max_size=40), signals)
def test_closed_accepts_nothing(
    ctx: TransitionContext, sequence: list[Signal], last: Signal
) -> None:
    applied = _run(ctx, sequence)
    if applied and applied[-1][0] == RunState.CLOSED:
        try:
            transition(RunState.CLOSED, last, ctx)
        except InvalidTransition:
            return
        raise AssertionError("closed run accepted a signal")


@settings(max_examples=200, deadline=None)
@given(contexts, st.lists(signals, max_size=40))
def test_answers_and_completion_never_count_as_rework(
    ctx: TransitionContext, sequence: list[Signal]
) -> None:
    for _, signal, effects in _run(ctx, sequence):
        if signal.kind in (SignalKind.CLARIFICATION_ANSWERED, SignalKind.ESCALATION_COMPLETED):
            assert not any(isinstance(e, CloseRun | IncrementAutoRetry) for e in effects)


@settings(max_examples=300, deadline=None)
@given(contexts, st.lists(signals, max_size=40))
def test_edits_never_close_or_escalate(ctx: TransitionContext, sequence: list[Signal]) -> None:
    """005: artifact_edited and controls_rechecked never change the run's state."""
    previous = RunState.OPENED
    for state, signal, effects in _run(ctx, sequence):
        if signal.kind in (SignalKind.ARTIFACT_EDITED, SignalKind.CONTROLS_RECHECKED):
            assert state == previous
            assert not any(isinstance(e, CloseRun | Escalate) for e in effects)
        previous = state


@settings(max_examples=300, deadline=None)
@given(contexts, st.lists(signals, max_size=40))
def test_no_pass_close_while_controls_are_pending(
    ctx: TransitionContext, sequence: list[Signal]
) -> None:
    """005: between an edit and its control re-check, no sign-off closes the run as pass."""
    pending = False
    for _, signal, effects in _run(ctx, sequence):
        if signal.kind == SignalKind.DECIDE and pending:
            assert not any(isinstance(e, CloseRun) and e.status == "pass" for e in effects)
            assert not any(isinstance(e, ProposeWaiver) for e in effects)
        for effect in effects:
            if isinstance(effect, SetControlsPending):
                pending = effect.pending


FAILURE_RESULTS = ("failed", "model_unavailable")


@settings(max_examples=300, deadline=None)
@given(contexts, st.lists(signals, max_size=40))
def test_failures_never_close_or_reach_sign_off(
    ctx: TransitionContext, sequence: list[Signal]
) -> None:
    """006: failed and model_unavailable results never close a run or reach sign-off."""
    for state, signal, effects in _run(ctx, sequence):
        if signal.kind in (SignalKind.AGENT_RESULT, SignalKind.REVIEW_RESULT) and (
            signal.payload.get("result") in FAILURE_RESULTS
        ):
            assert state not in (RunState.CLOSED, RunState.AWAITING_SIGN_OFF)
            assert not any(isinstance(e, CloseRun) for e in effects)


@settings(max_examples=300, deadline=None)
@given(contexts, st.lists(signals, max_size=40))
def test_model_unavailable_never_counts_as_retry(
    ctx: TransitionContext, sequence: list[Signal]
) -> None:
    """006: an outage is not the agent's fault, so it never uses a retry."""
    for _, signal, effects in _run(ctx, sequence):
        if signal.payload.get("result") == "model_unavailable":
            assert not any(isinstance(e, IncrementAutoRetry) for e in effects)
