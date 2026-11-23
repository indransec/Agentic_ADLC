"""``/usecases`` (007 contracts/api.md): submit, list, journey, verify."""

from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from adlc.api.deps import ActorDep, ServicesDep, traced
from adlc.api.errors import NotFound
from adlc.api.schemas.usecases import (
    Submitted,
    UseCaseJourney,
    UseCaseListItem,
    Verification,
)

router = APIRouter(prefix="/usecases")


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200, description="A short name")
    intake_text: str = Field(
        min_length=1,
        max_length=20_000,
        description="The problem, the people involved and the outcome wanted, in the "
        "submitter's words",
    )


@router.post("", status_code=201, response_model=Submitted, response_model_exclude_unset=True)
def submit(body: Submission, actor: ActorDep, services: ServicesDep) -> dict[str, str]:
    usecase_id = services.orchestration.submit_usecase(actor, body.name, body.intake_text)
    traced(usecase_id=usecase_id)
    return {"usecase_id": usecase_id}


@router.get("", response_model=list[UseCaseListItem], response_model_exclude_unset=True)
def list_usecases(
    actor: ActorDep,
    services: ServicesDep,
    mine: Annotated[
        bool, Query(description="Only those I submitted or take part in through a role")
    ] = False,
) -> list[dict[str, Any]]:
    return services.inbox.usecases(actor, mine)


@router.post("/{usecase_id}/verify", response_model=Verification, response_model_exclude_unset=True)
def verify(usecase_id: str, actor: ActorDep, services: ServicesDep) -> dict[str, Any]:
    """Any signed-in person may verify a use case's chain; the run is recorded under them."""
    traced(usecase_id=usecase_id)
    if services.orchestration.get_usecase(usecase_id) is None:
        raise NotFound(f"no use case {usecase_id}")
    return services.ledger.verify(actor, usecase_id).as_dict()


@router.get("/{usecase_id}", response_model=UseCaseJourney, response_model_exclude_unset=True)
def journey(usecase_id: str, actor: ActorDep, services: ServicesDep) -> dict[str, Any]:
    traced(usecase_id=usecase_id)
    return services.inbox.journey(usecase_id)
