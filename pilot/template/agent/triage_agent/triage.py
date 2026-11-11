"""Incident triage (FR-001; research R-05).

``SimulatedModel`` is the default, deterministic model: it applies the fill's routing rules with
the two mocked tools. ``DegradedModel`` is what the model swap fault switches to: it skips the
catalogue and misroutes a fixed share of requests (chosen by request id), so routing accuracy
drops by a predictable margin. Neither ever closes an incident or echoes personal data.
"""

import hashlib
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from triage_agent.fill import Fill
from triage_agent.pii import find_pii
from triage_agent.reference import Reference

ToolHook = Callable[[str], None]
CHARS_PER_TOKEN = 4
ANSWER_TOKENS = 60


class Reporter(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = ""
    department: str = ""
    persona: str = ""


class Incident(BaseModel):
    model_config = ConfigDict(extra="ignore")
    incident_id: str = Field(min_length=1, max_length=100)
    title: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=50_000)
    reporter: Reporter = Field(default_factory=Reporter)
    affected_service: str = Field(default="", max_length=200)
    urgency: Literal["low", "medium", "high"] = "medium"


class Assignment(BaseModel):
    incident_id: str
    category: str
    priority: str
    team: str
    reason: str
    review: bool = False
    confidence: float = 0.0
    tokens: int = 0
    model: str = "simulated"


def share_of(incident_id: str) -> float:
    """A stable number in [0, 1) for a request id."""
    digest = hashlib.sha256(incident_id.encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


class SimulatedModel:
    name = "simulated"

    def __init__(self, fill: Fill, reference: Reference) -> None:
        self.fill, self.reference = fill, reference

    def _text(self, incident: Incident) -> tuple[str, int]:
        """The text the model reads, cut to the token budget (FR-005)."""
        room = max(0, self.fill.settings.token_budget - ANSWER_TOKENS) * CHARS_PER_TOKEN
        text = f"{incident.title}\n{incident.description}".lower()[:room]
        return text, len(text) // CHARS_PER_TOKEN + ANSWER_TOKENS

    def _category(self, text: str) -> str | None:
        scores = {
            category: sum(word in text for word in words)
            for category, words in self.fill.routing.category_keywords.items()
        }
        best = max(scores.values(), default=0)
        return None if best == 0 else min(c for c, s in scores.items() if s == best)

    def _priority(self, incident: Incident, text: str) -> str:
        if any(word in text for word in self.fill.routing.p1_keywords):
            return "P1"
        return self.fill.routing.urgency_priority[incident.urgency]

    def triage(self, incident: Incident, on_tool: ToolHook | None = None) -> Assignment:
        note = on_tool or (lambda name: None)
        text, tokens = self._text(incident)
        rules = self.fill.routing
        if any(word in text for word in rules.security_keywords):
            team = self.reference.security
            return Assignment(
                incident_id=incident.incident_id,
                category="security",
                priority="P1",
                team=team,
                reason="Security signal in the incident: routed to Security Operations at P1.",
                confidence=0.95,
                tokens=tokens,
            )
        note("service_catalogue")
        service = self.reference.lookup_service(incident.affected_service)
        priority = self._priority(incident, text)
        if service is None:
            category = self._category(text) or "software"
            return Assignment(
                incident_id=incident.incident_id,
                category=category,
                priority=priority,
                team=self.reference.first_line,
                reason="Unknown service: not in the service catalogue, so assigned to the "
                "Service Desk for first-line triage.",
                review=True,
                confidence=0.4,
                tokens=tokens,
            )
        note("team_directory")
        owner = self.reference.lookup_team(service.owner)
        others = [
            s.name
            for s in self.reference.services.values()
            if s.id != service.id and s.name.lower() in text
        ]
        review = bool(others) and self.fill.thresholds.review_on_multi_service
        confidence = 0.6 if others else 0.9
        review = review or confidence < self.fill.thresholds.min_confidence_for_auto
        reason = (
            f"Affected service {service.name} is owned by "
            f"{owner.name if owner else service.owner} in the service catalogue."
        )
        if others:
            reason += f" Also mentions {', '.join(sorted(others))}: marked for review."
        return Assignment(
            incident_id=incident.incident_id,
            category=service.category,
            priority=priority,
            team=service.owner,
            reason=reason,
            review=review,
            confidence=confidence,
            tokens=tokens,
        )


class DegradedModel:
    """The model after a swap: no catalogue lookup, and a fixed share of wrong teams."""

    name = "degraded"

    def __init__(self, base: SimulatedModel, share: float = 0.5) -> None:
        self.base, self.share = base, share

    def triage(self, incident: Incident, on_tool: ToolHook | None = None) -> Assignment:
        answer = self.base.triage(incident)
        if share_of(incident.incident_id) >= self.share:
            return answer.model_copy(update={"model": self.name})
        teams = sorted(t for t in self.base.reference.teams if t != answer.team)
        wrong = teams[int(share_of(incident.incident_id + "#team") * len(teams))]
        return answer.model_copy(
            update={
                "team": wrong,
                "reason": "Assigned by keyword match without a catalogue lookup.",
                "confidence": 0.5,
                "model": self.name,
            }
        )


def leak(answer: Assignment, incident: Incident) -> Assignment:
    """The PII leak fault: the reason repeats the reporter's contact details (research R-05)."""
    found = find_pii(incident.description)
    if not found:
        return answer
    return answer.model_copy(update={"reason": f"{answer.reason} Contact: {', '.join(found)}."})
