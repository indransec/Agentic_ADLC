"""T006: who may act (shared by the inbox and the operations)."""

from adlc.inbox.rules import (
    can_answer,
    can_complete_escalation,
    can_decide_waiver,
    can_edit,
    is_coe,
    needed_sign_off_roles,
    sign_off_role,
)
from adlc.orchestration.service import Actor
from adlc.orchestration.states import TransitionContext

SPEC = {
    "terminal": {
        "actors": {"human_roles": [{"role": "owner", "raci": "A"}, {"role": "lead", "raci": "R"}]},
        "outcome_model": {"exception": {"set_by": ["risk"]}},
    }
}


def person(name: str, *roles: str) -> Actor:
    return Actor(name, frozenset(roles))


def ctx(**kw: object) -> TransitionContext:
    base: dict[str, object] = {"rule_roles": frozenset({"owner", "lead"}), "min_approvers": 2}
    base.update(kw)
    return TransitionContext(**base)  # type: ignore[arg-type]


def test_needed_roles_and_who_may_still_approve() -> None:
    two = ctx()
    assert needed_sign_off_roles(two) == {"owner", "lead"}
    one_done = ctx(approvals=(("ann", "owner"),))
    assert needed_sign_off_roles(one_done) == {"owner", "lead"}  # still one rule approver short
    assert sign_off_role(person("ann", "owner"), one_done) is None  # already approved
    assert sign_off_role(person("bob", "lead"), one_done) == "lead"
    done = ctx(approvals=(("ann", "owner"), ("bob", "lead")))
    assert needed_sign_off_roles(done) == frozenset()
    assert sign_off_role(person("cy", "owner"), done) is None


def test_conditional_role_stays_needed_after_the_rule_is_met() -> None:
    plus = ctx(
        min_approvers=1, required_plus_roles=frozenset({"arch"}), approvals=(("ann", "owner"),)
    )
    assert needed_sign_off_roles(plus) == {"arch"}
    assert sign_off_role(person("dee", "arch", "owner"), plus) == "arch"
    assert sign_off_role(person("ed", "lead"), plus) is None


def test_requests() -> None:
    assert can_answer(person("x", "lead"), "lead") and not can_answer(person("x", "owner"), "lead")
    assert not can_answer(person("x", "lead"), None)
    assert can_complete_escalation(person("x", "owner"), SPEC)
    assert not can_complete_escalation(person("x", "lead"), SPEC)
    assert can_decide_waiver(person("rita", "risk"), SPEC, proposed_by="ann")
    assert not can_decide_waiver(person("rita", "risk"), SPEC, proposed_by="rita")
    assert not can_decide_waiver(person("ann", "owner"), SPEC, proposed_by="bob")


def test_edit_and_coe() -> None:
    c = ctx()
    assert can_edit(person("x", "lead"), "awaiting_sign_off", c, SPEC)
    assert can_edit(person("x", "owner"), "escalated", c, SPEC)
    assert not can_edit(person("x", "lead"), "building", c, SPEC)
    assert not can_edit(person("x", "viewer"), "awaiting_sign_off", c, SPEC)
    assert not can_edit(
        Actor("agent:r", frozenset({"lead"}), kind="agent"), "awaiting_sign_off", c, SPEC
    )
    assert is_coe(person("x", "coe"), "coe") and not is_coe(person("x", "coe"), None)
