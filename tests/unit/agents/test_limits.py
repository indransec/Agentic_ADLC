"""T022: limits per tier with terminal overrides; the attempt budget (FR-014)."""

from adlc.agents.limits import Budget, Limits, limits_for
from adlc.config.settings import DEFAULT_AGENT_LIMITS, AgentLimitOverride


def test_tier_limits_and_overrides() -> None:
    overrides = {"T3": AgentLimitOverride(timeout_s=200)}
    assert limits_for(DEFAULT_AGENT_LIMITS, overrides, "coding", "T3") == Limits(16, 400_000, 200)
    assert limits_for(DEFAULT_AGENT_LIMITS, overrides, "standard", "T6") == Limits(14, 400_000, 240)


def test_budget_order_steps_tokens_time() -> None:
    now = [0.0]
    budget = Budget(Limits(steps=2, tokens=100, timeout_s=10), clock=lambda: now[0])
    assert budget.exceeded() is None and budget.remaining_s() == 10
    budget.spend(30, 20)  # every call is a step, corrections included
    assert (budget.steps, budget.tokens, budget.remaining_tokens()) == (1, 50, 50)
    budget.spend(40, 20)
    assert budget.exceeded() == "steps"
    tokens = Budget(Limits(steps=9, tokens=100, timeout_s=10), clock=lambda: now[0])
    tokens.spend(60, 40)
    assert tokens.exceeded() == "tokens"
    slow = Budget(Limits(steps=9, tokens=100, timeout_s=10), clock=lambda: now[0])
    now[0] = 10.5
    assert slow.exceeded() == "timeout" and slow.remaining_s() < 0
