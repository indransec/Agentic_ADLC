"""Who may act on what (007 research R-03). Shared by the inbox and the service operations, so an
item is listed exactly when its action would be allowed.

Roles always come from the pinned spec and the run's context (constitution I); nothing here names a
terminal or a role.
"""

from collections.abc import Mapping
from typing import Any, Protocol

from adlc.orchestration import spec_view
from adlc.orchestration.states import RunState, TransitionContext


class Actor(Protocol):
    """The parts of a signed-in actor the rules read (feature 003's ``Actor`` fits)."""

    @property
    def account_name(self) -> str: ...

    @property
    def roles(self) -> frozenset[str]: ...

    @property
    def kind(self) -> str: ...


EDITABLE_STATES = (RunState.AWAITING_SIGN_OFF, RunState.ESCALATED)


def needed_sign_off_roles(ctx: TransitionContext) -> frozenset[str]:
    """Roles whose approval the run still needs: open conditional roles, and the rule's roles
    while fewer than ``min_approvers`` distinct people have approved under them."""
    covered = {role for _, role in ctx.approvals if role in ctx.required_plus_roles}
    rule_people = {person for person, role in ctx.approvals if role in ctx.rule_roles}
    needed = set(ctx.required_plus_roles - covered)
    if len(rule_people) < ctx.min_approvers:
        needed |= ctx.rule_roles
    return frozenset(needed)


def sign_off_role(actor: Actor, ctx: TransitionContext) -> str | None:
    """The role under which ``actor`` may still approve, or None (already approved, or no role)."""
    if any(person == actor.account_name for person, _ in ctx.approvals):
        return None
    held = sorted(actor.roles & needed_sign_off_roles(ctx))
    plus = [r for r in held if r in ctx.required_plus_roles]
    chosen = plus or held
    return chosen[0] if chosen else None


def may_decide(actor: Actor, ctx: TransitionContext) -> bool:
    """Any sign-off decision (rework, exception, terminate) needs a sign-off role of the run."""
    return bool(actor.roles & (ctx.rule_roles | ctx.required_plus_roles))


def can_answer(actor: Actor, addressed_role: str | None) -> bool:
    return addressed_role is not None and addressed_role in actor.roles


def accountable(spec: Mapping[str, Any]) -> frozenset[str]:
    return spec_view.accountable_roles(spec)


def can_complete_escalation(actor: Actor, spec: Mapping[str, Any]) -> bool:
    return bool(actor.roles & accountable(spec))


def waiver_approvers(spec: Mapping[str, Any]) -> frozenset[str]:
    return spec_view.outcome_set_by(spec, "exception") or accountable(spec)


def can_decide_waiver(actor: Actor, spec: Mapping[str, Any], proposed_by: str) -> bool:
    return bool(actor.roles & waiver_approvers(spec)) and actor.account_name != proposed_by


def editor_roles(ctx: TransitionContext, spec: Mapping[str, Any]) -> frozenset[str]:
    return ctx.rule_roles | ctx.required_plus_roles | accountable(spec)


def can_edit(actor: Actor, state: str, ctx: TransitionContext, spec: Mapping[str, Any]) -> bool:
    return (
        actor.kind == "human"
        and RunState(state) in EDITABLE_STATES
        and bool(actor.roles & editor_roles(ctx, spec))
    )


def is_coe(actor: Actor, deadletter_role: str | None) -> bool:
    return deadletter_role is not None and deadletter_role in actor.roles
