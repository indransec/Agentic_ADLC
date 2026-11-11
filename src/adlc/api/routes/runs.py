"""``/runs/...`` (007 contracts/api.md): run detail and decisions.

Run ids contain slashes (``<use case>/<terminal>/run-<n>``), so they are path parameters; the
generic detail route is registered last so the specific routes match first.
"""

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from adlc.api.deps import ActorDep, ServicesDep, traced
from adlc.inbox.service import run_summary

router = APIRouter(prefix="/runs")


class Decision(BaseModel):
    """A sign-off decision. Extra keys are refused, so a body cannot name another actor or role
    (FR-002): the decision is always the signed-in person's."""

    model_config = ConfigDict(extra="forbid")
    decision: Literal["pass", "rework", "exception", "terminate"]
    comment: str | None = Field(default=None, max_length=4000)
    root_cause: str | None = Field(default=None, max_length=100)
    reason: str | None = Field(default=None, max_length=2000)
    fields: dict[str, Any] = Field(default_factory=dict)
    target_terminal: str | None = Field(default=None, max_length=20)
    expected_version: int = Field(ge=0)


class Completion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifacts: dict[str, list[dict[str, Any]]]
    expected_version: int = Field(ge=0)


@router.post("/{run_id:path}/decisions")
def decide(run_id: str, body: Decision, actor: ActorDep, services: ServicesDep) -> dict[str, Any]:
    traced(run_id=run_id)
    run = services.orchestration.decide(
        actor,
        run_id,
        body.decision,
        comment=body.comment,
        root_cause=body.root_cause,
        reason=body.reason,
        fields=body.fields,
        target_terminal=body.target_terminal,
        expected_version=body.expected_version,
    )
    return run_summary(run)


@router.post("/{run_id:path}/escalation")
def complete_escalation(
    run_id: str, body: Completion, actor: ActorDep, services: ServicesDep
) -> dict[str, Any]:
    traced(run_id=run_id)
    run = services.orchestration.complete_escalation(
        actor, run_id, body.artifacts, expected_version=body.expected_version
    )
    return run_summary(run)


def detail_router() -> APIRouter:
    """Registered after every other ``/runs`` router so its catch-all path matches last."""
    last = APIRouter(prefix="/runs")

    @last.get("/{run_id:path}")
    def detail(run_id: str, actor: ActorDep, services: ServicesDep) -> dict[str, Any]:
        traced(run_id=run_id)
        return services.inbox.detail(run_id, actor)

    return last
