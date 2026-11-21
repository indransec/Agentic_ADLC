"""Board sync health, reconciliation and requeue (feature 016; contracts/api-cli-settings.md).

CoE only (the role in ``ADLC_DEADLETTER_ROLE``, the same role that sees dead letters). The API
never polls the board; reconciliation runs in the request.
"""

from typing import Any

from fastapi import APIRouter, Request
from pydantic import ValidationError

from adlc.api.deps import ActorDep, Services, ServicesDep
from adlc.api.errors import NotFound
from adlc.config.settings import BoardSettings
from adlc.engagement.health import health
from adlc.engagement.wiring import BoardDisabled, Engagement, build
from adlc.orchestration.service import Actor, InvalidDecision, NotAuthorised

router = APIRouter(prefix="/board", tags=["board"])


def _coe(actor: Actor, services: Services) -> None:
    role = services.settings.deadletter_role
    if not role or role not in actor.roles:
        raise NotAuthorised(f"board sync needs the role {role}")


def _settings() -> BoardSettings | None:
    try:
        return BoardSettings()  # type: ignore[call-arg]
    except ValidationError:
        return None


def _engagement(request: Request, services: Services) -> Engagement:
    built: Engagement | None = getattr(request.app.state, "engagement", None)
    if built is None:
        settings = _settings()
        if settings is None or not settings.board_enabled:
            raise InvalidDecision("board sync is disabled (ADLC_BOARD_ENABLED is not true)")
        try:
            built = build(settings, services=services)
        except BoardDisabled as error:
            raise InvalidDecision(str(error)) from None
        request.app.state.engagement = built
    return built


@router.get("/health")
def board_health(request: Request, actor: ActorDep, services: ServicesDep) -> dict[str, Any]:
    _coe(actor, services)
    built: Engagement | None = getattr(request.app.state, "engagement", None)
    settings = built.settings if built is not None else _settings()
    enabled = settings is not None and settings.board_enabled
    return health(services.engine, enabled=enabled, now=services.clock.now())


@router.post("/reconciliations")
def reconcile(request: Request, actor: ActorDep, services: ServicesDep) -> dict[str, Any]:
    _coe(actor, services)
    return _engagement(request, services).reconciler.reconcile(actor)


@router.get("/reconciliations/{reconciliation_id}")
def reconciliation(
    reconciliation_id: int, request: Request, actor: ActorDep, services: ServicesDep
) -> dict[str, Any]:
    _coe(actor, services)
    report = _engagement(request, services).reconciler.report(reconciliation_id)
    if report is None:
        raise NotFound(f"no reconciliation {reconciliation_id}")
    return report


@router.post("/requeue/{usecase_id}")
def requeue(
    usecase_id: str, request: Request, actor: ActorDep, services: ServicesDep
) -> dict[str, Any]:
    _coe(actor, services)
    if not _engagement(request, services).projector.requeue(usecase_id, actor.account_name):
        raise NotFound(f"the board projection of {usecase_id} is not dead-lettered")
    return {"usecase_id": usecase_id, "requeued": True}
