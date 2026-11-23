"""``/changes`` (012 FR-012, contracts/api-changes.md): change requests decided by a person."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from adlc.api.deps import ActorDep, ServicesDep
from adlc.api.schemas.changes import ChangeRequest

router = APIRouter()


class ChangeDecision(BaseModel):
    approve: bool = Field(description="true approves the change, false rejects it")
    comment: str | None = Field(default=None, max_length=2000, description="Why")


@router.get("/changes", response_model=list[ChangeRequest], response_model_exclude_unset=True)
def changes(actor: ActorDep, services: ServicesDep) -> list[dict[str, Any]]:
    return services.changes.waiting(actor)


@router.post(
    "/changes/{change_id}/decision", response_model=ChangeRequest, response_model_exclude_unset=True
)
def decide(
    change_id: str, body: ChangeDecision, actor: ActorDep, services: ServicesDep
) -> dict[str, Any]:
    return services.changes.decide(actor, change_id, body.approve, body.comment)
