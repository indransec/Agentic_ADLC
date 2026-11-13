"""T010: every row of contracts/state-machine.md, and everything else refused (constitution III)."""

from collections.abc import Mapping
from typing import Any

import pytest

from adlc.orchestration.states import (
    ALLOWED_ACTOR,
    AUTOMATIC,
    OPEN,
    ActorType,
    CancelAllTimers,
    CancelTimer,
    ClearApprovals,
    CloseRun,
    DecideWaiver,
    Effect,
    Escalate,
    IncrementAutoRetry,
    InvalidTransition,
    ProposeWaiver,
    RecordClarification,
    RecordEvent,
    RecordSignOff,
    RunState,
    SetControlsPending,
    SetReturnState,
    Signal,
    SignalKind,
    StartTimer,
    StoreArtifacts,
    StoreControls,
    StoreRecommendation,
    TransitionContext,
    WithdrawWaiver,
    transition,
)

S = RunState
K = SignalKind
CTX = TransitionContext(
    max_clarification_rounds=2,
    max_auto_retries=3,
    min_approvers=1,
    rule_roles=frozenset({"owner", "second"}),
)


def sig(kind: SignalKind, payload: Mapping[str, Any] | None = None, actor: str = "x") -> Signal:
    return Signal(kind, ALLOWED_ACTOR[kind], actor, dict(payload or {}))


def go(
    state: RunState, signal: Signal, ctx: TransitionContext = CTX
) -> tuple[RunState, tuple[Effect, ...]]:
    out = transition(state, signal, ctx)
    return out.next_state, out.effects


PASS = {"decision": "pass", "role": "owner"}

ROWS: list[tuple[str, RunState, Signal, TransitionContext, RunState, tuple[Effect, ...]]] = [
    (
        "open escalated",
        S.OPENED,
        sig(K.OPEN_ESCALATED, {"trigger": "rework_limit"}),
        CTX,
        S.ESCALATED,
        (Escalate("rework_limit"),),
    ),
    (
        "prerequisites met",
        S.OPENED,
        sig(K.PREREQUISITES_RESULT, {"met": True}),
        CTX,
        S.BUILDING,
        (),
    ),
    (
        "prerequisites blocked",
        S.OPENED,
        sig(K.PREREQUISITES_RESULT, {"met": False}),
        CTX,
        S.BLOCKED,
        (),
    ),
    (
        "blocked re-check",
        S.BLOCKED,
        sig(K.EVENT_RECEIVED, {"event_type": "e"}),
        CTX,
        S.OPENED,
        (RecordEvent(),),
    ),
    (
        "blocked timer",
        S.BLOCKED,
        sig(K.TIMER, {"kind": "escalate_after"}),
        CTX,
        S.ESCALATED,
        (Escalate("timer"),),
    ),
    (
        "blocked terminate",
        S.BLOCKED,
        sig(K.DECIDE, {"decision": "terminate", "role": "owner"}),
        CTX,
        S.CLOSED,
        (RecordSignOff("terminate"), CloseRun("terminate")),
    ),
    (
        "artifacts",
        S.BUILDING,
        sig(K.AGENT_RESULT, {"result": "artifacts"}),
        CTX,
        S.CHECKING,
        (StoreArtifacts(),),
    ),
    (
        "agent clarification",
        S.BUILDING,
        sig(K.AGENT_RESULT, {"result": "clarification"}),
        CTX,
        S.AWAITING_CLARIFICATION,
        (RecordClarification("agent"), SetReturnState(S.BUILDING), StartTimer("clarification_sla")),
    ),
    (
        "agent clarification limit",
        S.BUILDING,
        sig(K.AGENT_RESULT, {"result": "clarification"}),
        TransitionContext(clarification_rounds=2),
        S.ESCALATED,
        (Escalate("clarification_limit"),),
    ),
    (
        "budget",
        S.BUILDING,
        sig(K.AGENT_RESULT, {"result": "budget_exceeded"}),
        CTX,
        S.ESCALATED,
        (Escalate("budget"),),
    ),
    (
        "controls pass",
        S.CHECKING,
        sig(K.CONTROLS_RESULT, {"passed": True}),
        CTX,
        S.REVIEWING,
        (StoreControls(),),
    ),
    (
        "controls retry",
        S.CHECKING,
        sig(K.CONTROLS_RESULT, {"passed": False}),
        CTX,
        S.BUILDING,
        (StoreControls(), IncrementAutoRetry()),
    ),
    (
        "controls retry limit",
        S.CHECKING,
        sig(K.CONTROLS_RESULT, {"passed": False}),
        TransitionContext(auto_retries=3, max_auto_retries=3),
        S.ESCALATED,
        (StoreControls(), Escalate("retry_limit")),
    ),
    (
        "recommendation",
        S.REVIEWING,
        sig(K.REVIEW_RESULT, {"result": "recommendation"}),
        CTX,
        S.AWAITING_SIGN_OFF,
        (StoreRecommendation(),),
    ),
    (
        "reviewer clarification",
        S.REVIEWING,
        sig(K.REVIEW_RESULT, {"result": "clarification"}),
        CTX,
        S.AWAITING_CLARIFICATION,
        (
            RecordClarification("reviewer"),
            SetReturnState(S.REVIEWING),
            StartTimer("clarification_sla"),
        ),
    ),
    (
        "reviewer clarification limit",
        S.REVIEWING,
        sig(K.REVIEW_RESULT, {"result": "clarification"}),
        TransitionContext(clarification_rounds=2),
        S.ESCALATED,
        (Escalate("clarification_limit"),),
    ),
    (
        "answer to building",
        S.AWAITING_CLARIFICATION,
        sig(K.CLARIFICATION_ANSWERED),
        TransitionContext(return_state=S.BUILDING),
        S.BUILDING,
        (CancelTimer("clarification_sla"), SetReturnState(None)),
    ),
    (
        "answer to reviewing",
        S.AWAITING_CLARIFICATION,
        sig(K.CLARIFICATION_ANSWERED),
        TransitionContext(return_state=S.REVIEWING),
        S.REVIEWING,
        (CancelTimer("clarification_sla"), SetReturnState(None)),
    ),
    (
        "clarification sla",
        S.AWAITING_CLARIFICATION,
        sig(K.TIMER, {"kind": "clarification_sla"}),
        CTX,
        S.ESCALATED,
        (Escalate("clarification_sla"),),
    ),
    (
        "pass, approvals below minimum",
        S.AWAITING_SIGN_OFF,
        sig(K.DECIDE, PASS, "p1"),
        TransitionContext(min_approvers=2, rule_roles=frozenset({"owner"})),
        S.AWAITING_SIGN_OFF,
        (RecordSignOff("pass"),),
    ),
    (
        "pass, minimum reached",
        S.AWAITING_SIGN_OFF,
        sig(K.DECIDE, PASS, "p2"),
        TransitionContext(
            min_approvers=2, rule_roles=frozenset({"owner"}), approvals=(("p1", "owner"),)
        ),
        S.CLOSED,
        (RecordSignOff("pass"), CloseRun("pass")),
    ),
    (
        "pass, same person twice counts once",
        S.AWAITING_SIGN_OFF,
        sig(K.DECIDE, PASS, "p1"),
        TransitionContext(
            min_approvers=2, rule_roles=frozenset({"owner"}), approvals=(("p1", "owner"),)
        ),
        S.AWAITING_SIGN_OFF,
        (),
    ),
    (
        "pass, plus approver still needed",
        S.AWAITING_SIGN_OFF,
        sig(K.DECIDE, PASS, "p1"),
        TransitionContext(rule_roles=frozenset({"owner"}), required_plus_roles=frozenset({"arch"})),
        S.AWAITING_SIGN_OFF,
        (RecordSignOff("pass"),),
    ),
    (
        "pass, plus approver completes",
        S.AWAITING_SIGN_OFF,
        sig(K.DECIDE, {"decision": "pass", "role": "arch"}, "p2"),
        TransitionContext(
            rule_roles=frozenset({"owner"}),
            required_plus_roles=frozenset({"arch"}),
            approvals=(("p1", "owner"),),
        ),
        S.CLOSED,
        (RecordSignOff("pass"), CloseRun("pass")),
    ),
    (
        "rework",
        S.AWAITING_SIGN_OFF,
        sig(K.DECIDE, {"decision": "rework", "role": "owner"}),
        CTX,
        S.CLOSED,
        (RecordSignOff("rework"), CloseRun("rework")),
    ),
    (
        "exception proposed",
        S.AWAITING_SIGN_OFF,
        sig(K.DECIDE, {"decision": "exception", "role": "owner"}),
        CTX,
        S.AWAITING_SIGN_OFF,
        (RecordSignOff("exception"), ProposeWaiver()),
    ),
    (
        "waiver approved",
        S.AWAITING_SIGN_OFF,
        sig(K.WAIVER_DECISION, {"approve": True}),
        TransitionContext(pending_waiver=True),
        S.CLOSED,
        (DecideWaiver(approve=True), CloseRun("exception")),
    ),
    (
        "waiver rejected",
        S.AWAITING_SIGN_OFF,
        sig(K.WAIVER_DECISION, {"approve": False}),
        TransitionContext(pending_waiver=True),
        S.AWAITING_SIGN_OFF,
        (DecideWaiver(approve=False),),
    ),
    (
        "terminate at sign-off",
        S.AWAITING_SIGN_OFF,
        sig(K.DECIDE, {"decision": "terminate", "role": "owner"}),
        CTX,
        S.CLOSED,
        (RecordSignOff("terminate"), CloseRun("terminate")),
    ),
    (
        "escalation completed",
        S.ESCALATED,
        sig(K.ESCALATION_COMPLETED),
        CTX,
        S.AWAITING_SIGN_OFF,
        (StoreArtifacts(),),
    ),
    (
        "terminate escalated",
        S.ESCALATED,
        sig(K.DECIDE, {"decision": "terminate", "role": "owner"}),
        CTX,
        S.CLOSED,
        (RecordSignOff("terminate"), CloseRun("terminate")),
    ),
]


@pytest.mark.parametrize(
    ("state", "signal", "ctx", "expected_state", "expected_effects"),
    [row[1:] for row in ROWS],
    ids=[row[0] for row in ROWS],
)
def test_table_row(
    state: RunState,
    signal: Signal,
    ctx: TransitionContext,
    expected_state: RunState,
    expected_effects: tuple[Effect, ...],
) -> None:
    assert go(state, signal, ctx) == (expected_state, expected_effects)


@pytest.mark.parametrize("state", sorted(OPEN - {S.ESCALATED}))
def test_escalate_after_from_every_open_state(state: RunState) -> None:
    assert go(state, sig(K.TIMER, {"kind": "escalate_after"})) == (
        S.ESCALATED,
        (Escalate("timer"),),
    )


def test_escalated_run_does_not_escalate_again() -> None:
    assert go(S.ESCALATED, sig(K.TIMER, {"kind": "escalate_after"})) == (S.ESCALATED, ())


@pytest.mark.parametrize("state", sorted(OPEN - {S.BLOCKED}))
def test_event_received_is_recorded(state: RunState) -> None:
    assert go(state, sig(K.EVENT_RECEIVED, {"event_type": "e"})) == (state, (RecordEvent(),))


@pytest.mark.parametrize("state", sorted(AUTOMATIC))
def test_interrupted_step_counts_as_retry(state: RunState) -> None:
    assert go(state, sig(K.STEP_INTERRUPTED)) == (state, (IncrementAutoRetry(),))
    limit = TransitionContext(auto_retries=3, max_auto_retries=3)
    assert go(state, sig(K.STEP_INTERRUPTED), limit) == (
        S.ESCALATED,
        (Escalate("retry_limit"),),
    )


@pytest.mark.parametrize("state", sorted(OPEN))
def test_lifecycle_ended_closes_any_open_run(state: RunState) -> None:
    assert go(state, sig(K.LIFECYCLE_ENDED)) == (
        S.CLOSED,
        (CancelAllTimers(), CloseRun("terminate")),
    )


def test_pending_waiver_blocks_other_decisions() -> None:
    ctx = TransitionContext(pending_waiver=True, rule_roles=frozenset({"owner"}))
    for decision in ("pass", "rework", "exception"):
        with pytest.raises(InvalidTransition):
            go(S.AWAITING_SIGN_OFF, sig(K.DECIDE, {"decision": decision, "role": "owner"}), ctx)
    assert (
        go(S.AWAITING_SIGN_OFF, sig(K.DECIDE, {"decision": "terminate", "role": "owner"}), ctx)[0]
        == S.CLOSED
    )


def test_waiver_decision_needs_pending_waiver() -> None:
    with pytest.raises(InvalidTransition):
        go(S.AWAITING_SIGN_OFF, sig(K.WAIVER_DECISION, {"approve": True}))


def test_pass_role_must_belong_to_the_rule() -> None:
    with pytest.raises(InvalidTransition):
        go(S.AWAITING_SIGN_OFF, sig(K.DECIDE, {"decision": "pass", "role": "stranger"}))


# ------------------------------------------------------------------ everything else is refused

SAMPLE_PAYLOADS: dict[SignalKind, list[dict[str, Any]]] = {
    K.PREREQUISITES_RESULT: [{"met": True}, {"met": False}],
    K.EVENT_RECEIVED: [{"event_type": "e"}],
    K.AGENT_RESULT: [
        {"result": r}
        for r in ("artifacts", "clarification", "budget_exceeded", "failed", "model_unavailable")
    ],
    K.CONTROLS_RESULT: [{"passed": True}, {"passed": False}],
    K.REVIEW_RESULT: [{"result": "recommendation"}, {"result": "clarification"}],
    K.CLARIFICATION_ANSWERED: [{}],
    K.DECIDE: [
        {"decision": d, "role": "owner"} for d in ("pass", "rework", "exception", "terminate")
    ],
    K.WAIVER_DECISION: [{"approve": True}, {"approve": False}],
    K.ESCALATION_COMPLETED: [{}],
    K.TIMER: [{"kind": "escalate_after"}, {"kind": "clarification_sla"}],
    K.OPEN_ESCALATED: [{"trigger": "rework_limit"}],
    K.STEP_INTERRUPTED: [{}],
    K.LIFECYCLE_ENDED: [{}],
    K.ARTIFACT_EDITED: [{"artifacts": {}}],
    K.CONTROLS_RECHECKED: [{"results": []}],
    K.EVIDENCE_CHANGED: [{}],
}

ALLOWED: set[tuple[RunState, SignalKind]] = {
    (S.OPENED, K.OPEN_ESCALATED),
    (S.OPENED, K.PREREQUISITES_RESULT),
    (S.BLOCKED, K.DECIDE),
    (S.BUILDING, K.AGENT_RESULT),
    (S.CHECKING, K.CONTROLS_RESULT),
    (S.REVIEWING, K.REVIEW_RESULT),
    (S.AWAITING_CLARIFICATION, K.CLARIFICATION_ANSWERED),
    (S.AWAITING_SIGN_OFF, K.DECIDE),
    (S.AWAITING_SIGN_OFF, K.WAIVER_DECISION),
    (S.ESCALATED, K.ESCALATION_COMPLETED),
    (S.ESCALATED, K.DECIDE),
    *((s, K.TIMER) for s in OPEN),
    *((s, K.EVENT_RECEIVED) for s in OPEN),
    *((s, K.STEP_INTERRUPTED) for s in AUTOMATIC),
    *((s, K.LIFECYCLE_ENDED) for s in OPEN),
    *(
        (s, k)
        for s in (S.AWAITING_SIGN_OFF, S.ESCALATED)
        for k in (K.ARTIFACT_EDITED, K.CONTROLS_RECHECKED)
    ),
    (S.AWAITING_SIGN_OFF, K.EVIDENCE_CHANGED),
}


@pytest.mark.parametrize("state", list(S))
@pytest.mark.parametrize("kind", list(K))
def test_pairs_outside_the_table_are_refused(state: RunState, kind: SignalKind) -> None:
    if (state, kind) in ALLOWED:
        return
    for payload in SAMPLE_PAYLOADS[kind]:
        with pytest.raises(InvalidTransition):
            transition(state, sig(kind, payload), TransitionContext(pending_waiver=True))


@pytest.mark.parametrize("kind", list(K))
@pytest.mark.parametrize("actor", list(ActorType))
def test_wrong_actor_is_refused(kind: SignalKind, actor: ActorType) -> None:
    if actor == ALLOWED_ACTOR[kind]:
        return
    for state in S:
        for payload in SAMPLE_PAYLOADS[kind]:
            with pytest.raises(InvalidTransition, match="actor"):
                transition(state, Signal(kind, actor, "x", payload), CTX)


def test_closed_accepts_nothing() -> None:
    for kind in K:
        for payload in SAMPLE_PAYLOADS[kind]:
            with pytest.raises(InvalidTransition):
                transition(S.CLOSED, sig(kind, payload), CTX)


def test_unknown_timer_and_decision_values_are_refused() -> None:
    with pytest.raises(InvalidTransition):
        go(S.BLOCKED, sig(K.TIMER, {"kind": "review_due"}))
    with pytest.raises(InvalidTransition):
        go(S.AWAITING_SIGN_OFF, sig(K.DECIDE, {"decision": "escalate", "role": "owner"}))


def test_artifact_edited_keeps_the_state() -> None:
    """005: an edit stores the person's version and withdraws a pending waiver; no state change."""
    edit = sig(K.ARTIFACT_EDITED, {"artifacts": {}})
    assert go(S.AWAITING_SIGN_OFF, edit) == (
        S.AWAITING_SIGN_OFF,
        (StoreArtifacts(), ClearApprovals(), SetControlsPending(True)),
    )
    assert go(S.AWAITING_SIGN_OFF, edit, TransitionContext(pending_waiver=True)) == (
        S.AWAITING_SIGN_OFF,
        (StoreArtifacts(), ClearApprovals(), WithdrawWaiver(), SetControlsPending(True)),
    )
    assert go(S.ESCALATED, edit) == (S.ESCALATED, (StoreArtifacts(), ClearApprovals()))
    recheck = sig(K.CONTROLS_RECHECKED, {"results": []})
    assert go(S.AWAITING_SIGN_OFF, recheck) == (
        S.AWAITING_SIGN_OFF,
        (StoreControls(), SetControlsPending(False)),
    )


def test_no_pass_or_exception_while_controls_are_pending() -> None:
    """005 FR-010: decisions are made on re-checked content; rework and terminate stay open."""
    pending = TransitionContext(rule_roles=frozenset({"owner"}), controls_pending=True)
    for decision in ("pass", "exception"):
        payload = {"decision": decision, "role": "owner"}
        with pytest.raises(InvalidTransition, match="re-run after an edit"):
            transition(S.AWAITING_SIGN_OFF, sig(K.DECIDE, payload), pending)
    rework = sig(K.DECIDE, {"decision": "rework", "role": "owner"})
    assert transition(S.AWAITING_SIGN_OFF, rework, pending).next_state == S.CLOSED


def test_awaited_controls_hold_pass_until_rechecked() -> None:
    """012: a failed control that awaits a person's action (e.g. a change approval) refuses
    pass; that action re-runs the controls; rework and terminate stay open."""
    waiting = TransitionContext(rule_roles=frozenset({"owner"}), awaiting=("CTL-T6-07",))
    passing = sig(K.DECIDE, {"decision": "pass", "role": "owner"})
    with pytest.raises(InvalidTransition, match="CTL-T6-07 wait for an action"):
        transition(S.AWAITING_SIGN_OFF, passing, waiting)
    rework = sig(K.DECIDE, {"decision": "rework", "role": "owner"})
    assert transition(S.AWAITING_SIGN_OFF, rework, waiting).next_state == S.CLOSED
    changed = sig(K.EVIDENCE_CHANGED, {})
    assert go(S.AWAITING_SIGN_OFF, changed, waiting) == (
        S.AWAITING_SIGN_OFF,
        (SetControlsPending(True),),
    )
    with pytest.raises(InvalidTransition):  # nothing awaited: nothing to re-run
        transition(S.AWAITING_SIGN_OFF, changed, TransitionContext())


def test_failed_build_attempt_is_an_auto_retry() -> None:
    """006: output still unfit after corrections counts like a failed blocking control."""
    failed = sig(K.AGENT_RESULT, {"result": "failed", "reason": "missing column kpi_id"})
    assert go(S.BUILDING, failed, TransitionContext(max_auto_retries=2, auto_retries=1)) == (
        S.BUILDING,
        (IncrementAutoRetry(),),
    )
    assert go(S.BUILDING, failed, TransitionContext(max_auto_retries=2, auto_retries=2)) == (
        S.ESCALATED,
        (Escalate("retry_limit"),),
    )


def test_model_unavailable_and_reviewer_failure_escalate() -> None:
    """006: after the outage limit, and when the reviewer's output never fits."""
    assert go(S.BUILDING, sig(K.AGENT_RESULT, {"result": "model_unavailable"})) == (
        S.ESCALATED,
        (Escalate("model_unavailable"),),
    )
    assert go(S.REVIEWING, sig(K.REVIEW_RESULT, {"result": "model_unavailable"})) == (
        S.ESCALATED,
        (Escalate("model_unavailable"),),
    )
    assert go(S.REVIEWING, sig(K.REVIEW_RESULT, {"result": "failed", "reason": "r"})) == (
        S.ESCALATED,
        (Escalate("reviewer_failed"),),
    )
