"""Where a run's time went (feature 013, research R-04), from its state transitions.

Intervals are wall-clock time between transitions (the engine's clock); an open run's last
interval ends now. States map to fixed categories; nothing here names a terminal.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

CATEGORIES = ("agent", "reviewer", "clarification", "people", "blocked", "other")
CATEGORY_OF = {
    "building": "agent",
    "checking": "reviewer",
    "reviewing": "reviewer",
    "awaiting_clarification": "clarification",
    "awaiting_sign_off": "people",
    "escalated": "people",
    "blocked": "blocked",
}
CLOSED = "closed"


@dataclass(frozen=True)
class Transition:
    to_state: str
    at: datetime


def split(transitions: Sequence[Transition], *, now: datetime) -> dict[str, float]:
    """Seconds per category; the time after ``closed`` counts nowhere."""
    found = dict.fromkeys(CATEGORIES, 0.0)
    ordered = sorted(transitions, key=lambda t: t.at)
    for i, current in enumerate(ordered):
        following = ordered[i + 1] if i + 1 < len(ordered) else None
        if current.to_state == CLOSED:
            continue
        end = following.at if following is not None else now
        found[CATEGORY_OF.get(current.to_state, "other")] += max(
            0.0, (end - current.at).total_seconds()
        )
    return found
