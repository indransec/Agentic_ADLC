"""The decision form, built from the pinned spec (007 FR-009, research R-04).

The form mirrors feature 003's validation, so what the form asks for is exactly what a decision
needs. Nothing here names a terminal, role, outcome route or field (constitution I).
"""

from collections.abc import Callable, Collection, Mapping
from typing import Any

from adlc.inbox import rules
from adlc.inbox.rules import Actor
from adlc.orchestration import routing, spec_view
from adlc.orchestration.states import RunState, TransitionContext
from adlc.orchestration.store import RunRow
from adlc.spec_toolkit.registry import SpecRegistry

DECISION_ORDER = ("pass", "rework", "exception", "terminate")
RESOLVER_KIND = "terminal_resolver"


def build_form(
    *,
    spec: Mapping[str, Any],
    run: RunRow,
    ctx: TransitionContext,
    actor: Actor,
    registry: SpecRegistry,
    destination_kind: Callable[[str], str | None],
    catalogue_root_causes: Collection[str],
    pinned_terminals: Collection[str],
) -> dict[str, Any]:
    rights = spec_view.status_rights(spec, "human")
    outcomes = []
    for status in DECISION_ORDER:
        if status not in rights or spec_view.outcome_not_allowed(spec, status):
            continue
        if status != "terminate":
            route = registry.outcome_route(run.terminal_id, status, version=run.spec_version)
            if status != "rework" and (route is None or route.kind == "disabled"):
                continue
        outcomes.append(status)

    causes = list(spec_view.rework_causes(spec) or sorted(catalogue_root_causes))
    needs_target = []
    for cause in causes:
        route = registry.outcome_route(run.terminal_id, "rework", cause, run.spec_version)
        if route is not None and destination_kind(route.destination) == RESOLVER_KIND:
            needs_target.append(cause)

    pass_route = registry.outcome_route(run.terminal_id, "pass", version=run.spec_version)
    emitted = routing.emitted_values(spec, run.artifacts, {"usecase_id": run.usecase_id}, {})
    at_sign_off = run.state == RunState.AWAITING_SIGN_OFF
    decider = rules.may_decide(actor, ctx) and not run.controls_pending
    terminate_roles = spec_view.outcome_set_by(spec, "terminate") or (
        ctx.rule_roles | ctx.required_plus_roles
    )
    return {
        "outcomes": outcomes,
        "requires": {s: list(spec_view.outcome_requires(spec, s)) for s in outcomes},
        "root_causes": causes,
        "target_terminal_for": needs_target,
        "target_terminals": sorted(pinned_terminals),
        "typed_fields": list(emitted.missing),
        "alternatives": list(pass_route.alternatives) if pass_route is not None else [],
        "reason_required_unless": (run.recommendation or {}).get("status"),
        "sign_off_role": rules.sign_off_role(actor, ctx) if at_sign_off else None,
        "can_decide": at_sign_off and decider and not ctx.pending_waiver,
        "can_terminate": bool(actor.roles & terminate_roles)
        and run.state in (RunState.AWAITING_SIGN_OFF, RunState.ESCALATED, RunState.BLOCKED),
        "can_edit": rules.can_edit(actor, str(run.state), ctx, spec),
        "controls_pending": run.controls_pending,
        "waiver_pending": ctx.pending_waiver,
    }
