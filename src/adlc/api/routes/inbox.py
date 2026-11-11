"""``/inbox`` (007 FR-006): what is waiting for the signed-in person."""

from typing import Any

from fastapi import APIRouter

from adlc.api.deps import ActorDep, ServicesDep

router = APIRouter()


@router.get("/inbox")
def inbox(actor: ActorDep, services: ServicesDep) -> list[dict[str, Any]]:
    return services.inbox.items(actor)
