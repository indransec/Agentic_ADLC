"""``/changes`` (012 FR-012, contracts/api-changes.md): change requests decided by a person."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from adlc.api.deps import ActorDep, ServicesDep

router = APIRouter()


class ChangeDecision(BaseModel):
    approve: bool
    comment: str | None = Field(default=None, max_length=2000)


@router.get("/changes")
def changes(actor: ActorDep, services: ServicesDep) -> list[dict[str, Any]]:
    return services.changes.waiting(actor)


@router.post("/changes/{change_id}/decision")
def decide(
    change_id: str, body: ChangeDecision, actor: ActorDep, services: ServicesDep
) -> dict[str, Any]:
    return services.changes.decide(actor, change_id, body.approve, body.comment)
