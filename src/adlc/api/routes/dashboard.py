"""``/dashboard`` (feature 013, contracts/api-dashboard.md): read-only lifecycle views. Every
signed-in person may read every use case (FR-009)."""

from typing import Annotated, Any

from fastapi import APIRouter, Query

from adlc.api.deps import ActorDep, ServicesDep
from adlc.api.schemas.dashboard import (
    ActivityEntry,
    Journey,
    Kpis,
    Portfolio,
    RunTimeline,
)

router = APIRouter(prefix="/dashboard")


@router.get(
    "/usecases/{usecase_id}/journey", response_model=Journey, response_model_exclude_unset=True
)
def journey(usecase_id: str, actor: ActorDep, services: ServicesDep) -> dict[str, Any]:
    return services.dashboard.journey(usecase_id)


@router.get("/usecases/{usecase_id}/kpis", response_model=Kpis, response_model_exclude_unset=True)
def kpis(usecase_id: str, actor: ActorDep, services: ServicesDep) -> dict[str, Any]:
    return services.dashboard.kpis(usecase_id)


@router.get("/portfolio", response_model=Portfolio, response_model_exclude_unset=True)
def portfolio(
    actor: ActorDep,
    services: ServicesDep,
    risk_tier: Annotated[str | None, Query(description="Only use cases of this risk tier")] = None,
    status: Annotated[str | None, Query(description="Only use cases in this status")] = None,
) -> dict[str, Any]:
    return services.dashboard.portfolio(risk_tier, status)


@router.get("/activity", response_model=list[ActivityEntry], response_model_exclude_unset=True)
def activity(
    actor: ActorDep,
    services: ServicesDep,
    usecase_id: Annotated[str | None, Query(description="Only this use case")] = None,
    terminal_id: Annotated[str | None, Query(description="Only this terminal")] = None,
    actor_type: Annotated[
        str | None, Query(description="agent, reviewer, human, orchestrator or system")
    ] = None,
    step: Annotated[str | None, Query(description="Only this run step")] = None,
    limit: Annotated[int, Query(description="At most this many actions (1 to 1000)")] = 200,
) -> list[dict[str, Any]]:
    return services.dashboard.activity(usecase_id, terminal_id, actor_type, step, limit)


@router.get(
    "/runs/{run_id:path}/timeline", response_model=RunTimeline, response_model_exclude_unset=True
)
def timeline(run_id: str, actor: ActorDep, services: ServicesDep) -> dict[str, Any]:
    return services.dashboard.run_timeline(run_id)
