"""``/inbox`` (007 FR-006): what is waiting for the signed-in person."""

from typing import Any

from fastapi import APIRouter

from adlc.api.deps import ActorDep, ServicesDep
from adlc.api.schemas.inbox import InboxItem

router = APIRouter()


@router.get("/inbox", response_model=list[InboxItem], response_model_exclude_unset=True)
def inbox(actor: ActorDep, services: ServicesDep) -> list[dict[str, Any]]:
    return services.inbox.items(actor)
