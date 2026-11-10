"""Limits of one agent attempt (006 FR-014, FR-015; research R-07).

Every model call counts as a step, corrections included. Tokens are input plus output across the
attempt. The time left in the attempt is each call's timeout.
"""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from adlc.config.settings import AgentLimit, AgentLimitOverride


@dataclass(frozen=True)
class Limits:
    steps: int
    tokens: int
    timeout_s: float


def limits_for(
    tiers: Mapping[str, AgentLimit],
    overrides: Mapping[str, AgentLimitOverride],
    tier: str,
    terminal: str,
) -> Limits:
    base = tiers[tier]
    over = overrides.get(terminal)
    return Limits(
        steps=over.steps if over and over.steps else base.steps,
        tokens=over.tokens if over and over.tokens else base.tokens,
        timeout_s=over.timeout_s if over and over.timeout_s else base.timeout_s,
    )


@dataclass
class Budget:
    limits: Limits
    clock: Callable[[], float] = time.monotonic
    steps: int = 0
    tokens: int = 0
    started: float = field(default=0.0)

    def __post_init__(self) -> None:
        self.started = self.clock()

    def exceeded(self) -> str | None:
        """The limit reached, checked before each call: steps, then tokens, then time."""
        if self.steps >= self.limits.steps:
            return "steps"
        if self.tokens >= self.limits.tokens:
            return "tokens"
        if self.remaining_s() <= 0:
            return "timeout"
        return None

    def remaining_s(self) -> float:
        return self.limits.timeout_s - (self.clock() - self.started)

    def remaining_tokens(self) -> int:
        return max(self.limits.tokens - self.tokens, 0)

    def spend(self, tokens_in: int, tokens_out: int) -> None:
        self.steps += 1
        self.tokens += tokens_in + tokens_out
