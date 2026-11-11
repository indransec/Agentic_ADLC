"""``/usecases`` (007 contracts/api.md): submit, list, journey, verify."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from adlc.api.deps import ActorDep, ServicesDep, traced

router = APIRouter(prefix="/usecases")


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    intake_text: str = Field(min_length=1, max_length=20_000)


@router.post("", status_code=201)
def submit(body: Submission, actor: ActorDep, services: ServicesDep) -> dict[str, str]:
    usecase_id = services.orchestration.submit_usecase(actor, body.name, body.intake_text)
    traced(usecase_id=usecase_id)
    return {"usecase_id": usecase_id}


@router.get("")
def list_usecases(
    actor: ActorDep, services: ServicesDep, mine: bool = False
) -> list[dict[str, Any]]:
    return services.inbox.usecases(actor, mine)


@router.get("/{usecase_id}")
def journey(usecase_id: str, actor: ActorDep, services: ServicesDep) -> dict[str, Any]:
    traced(usecase_id=usecase_id)
    return services.inbox.journey(usecase_id)
