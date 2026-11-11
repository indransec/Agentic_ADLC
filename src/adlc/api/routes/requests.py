"""Clarification answers, waiver decisions and dead letters (007 FR-015 to FR-018).

Clarification ids contain slashes, so they are path parameters.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field

from adlc.api.deps import ActorDep, ServicesDep, traced
from adlc.api.errors import NotFound
from adlc.inbox.service import run_summary

router = APIRouter()


class Answers(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: list[str] = Field(min_length=1, max_length=50)


class WaiverDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: bool
    comment: str | None = Field(default=None, max_length=4000)


@router.post("/clarifications/{clarification_id:path}/answers")
def answer(
    clarification_id: str, body: Answers, actor: ActorDep, services: ServicesDep
) -> dict[str, Any]:
    if not services.inbox.clarification_exists(clarification_id):
        raise NotFound(f"no clarification {clarification_id}")
    run = services.orchestration.answer_clarification(actor, clarification_id, body.answers)
    traced(run_id=run.run_id, usecase_id=run.usecase_id)
    return run_summary(run)


@router.post("/waivers/{waiver_id}/decision")
def decide_waiver(
    waiver_id: str, body: WaiverDecision, actor: ActorDep, services: ServicesDep
) -> dict[str, Any]:
    if not services.inbox.waiver_exists(waiver_id):
        raise NotFound(f"no waiver {waiver_id}")
    run = services.orchestration.decide_waiver(actor, waiver_id, body.approve, body.comment)
    traced(run_id=run.run_id, usecase_id=run.usecase_id)
    return run_summary(run)


@router.get("/dead-letters")
def dead_letters(actor: ActorDep, services: ServicesDep) -> list[dict[str, Any]]:
    return [dict(d) for d in services.orchestration.list_dead_letters(actor)]


@router.post("/dead-letters/{event_id}/requeue", status_code=204)
def requeue(event_id: UUID, actor: ActorDep, services: ServicesDep) -> Response:
    services.orchestration.requeue(actor, event_id)
    return Response(status_code=204)
