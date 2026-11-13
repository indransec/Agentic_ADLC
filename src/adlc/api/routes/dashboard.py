"""``/dashboard`` (feature 013, contracts/api-dashboard.md): read-only lifecycle views. Every
signed-in person may read every use case (FR-009)."""

from typing import Any

from fastapi import APIRouter

from adlc.api.deps import ActorDep, ServicesDep

router = APIRouter(prefix="/dashboard")


@router.get("/usecases/{usecase_id}/journey")
def journey(usecase_id: str, actor: ActorDep, services: ServicesDep) -> dict[str, Any]:
    return services.dashboard.journey(usecase_id)


@router.get("/usecases/{usecase_id}/kpis")
def kpis(usecase_id: str, actor: ActorDep, services: ServicesDep) -> dict[str, Any]:
    return services.dashboard.kpis(usecase_id)


@router.get("/portfolio")
def portfolio(
    actor: ActorDep,
    services: ServicesDep,
    risk_tier: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    return services.dashboard.portfolio(risk_tier, status)


@router.get("/activity")
def activity(
    actor: ActorDep,
    services: ServicesDep,
    usecase_id: str | None = None,
    terminal_id: str | None = None,
    actor_type: str | None = None,
    step: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    return services.dashboard.activity(usecase_id, terminal_id, actor_type, step, limit)


@router.get("/runs/{run_id:path}/timeline")
def timeline(run_id: str, actor: ActorDep, services: ServicesDep) -> dict[str, Any]:
    return services.dashboard.run_timeline(run_id)
