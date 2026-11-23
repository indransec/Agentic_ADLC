"""Answers of ``/events/proposed`` (feature 012): events an agent proposed, and decisions."""

from typing import Any

from adlc.api.schemas.base import ApiModel


class ProposedEvent(ApiModel):
    """A proposal row of the run's artifact table (its values as the agent wrote them)."""

    event_id: Any
    event_type: Any
    raised_at: Any
    routed_to: Any
    run_id: str
    usecase_id: str
    terminal_id: str


class ProposedEventDecided(ApiModel):
    event_id: str
    event_type: Any
    confirmed: bool
    by: str
    comment: str
    raised_event_id: str | None = None  # only when confirmed (absent otherwise)
