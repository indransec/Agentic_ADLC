"""``/events/proposed`` (012 FR-007, contracts/api-changes.md): agent-proposed lifecycle events,
confirmed or dismissed by a person."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from adlc.api.deps import ActorDep, ServicesDep

router = APIRouter()


class EventDecision(BaseModel):
    confirm: bool
    comment: str | None = Field(default=None, max_length=2000)


@router.get("/events/proposed")
def proposed(actor: ActorDep, services: ServicesDep) -> list[dict[str, Any]]:
    return services.proposed_events.waiting(actor)


@router.post("/events/proposed/{usecase_id}/{terminal_id}/{run_number}/{event_id}")
def decide(
    usecase_id: str,
    terminal_id: str,
    run_number: str,
    event_id: str,
    body: EventDecision,
    actor: ActorDep,
    services: ServicesDep,
) -> dict[str, Any]:
    run_id = f"{usecase_id}/{terminal_id}/{run_number}"  # run ids contain slashes
    return services.proposed_events.decide(actor, run_id, event_id, body.confirm, body.comment)
