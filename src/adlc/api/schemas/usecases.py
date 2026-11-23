"""Answers of ``/usecases``: submission, the list, a use case's journey and ledger verification."""

from typing import Any

from adlc.api.schemas.base import ApiModel, CostTotals, RunSummary, Timestamp


class Submitted(ApiModel):
    usecase_id: str


class UseCaseListItem(ApiModel):
    usecase_id: str
    name: str
    submitted_by: str
    risk_tier: str | None
    status: str
    submitted_at: Timestamp
    open_runs: int


class UseCase(ApiModel):
    usecase_id: str
    name: str
    intake_text: str
    submitted_by: str
    risk_tier: str | None
    status: str


class TerminalSummary(ApiModel):
    terminal_id: str
    runs: int
    reworks: int
    clarification_rounds: int
    escalations: int
    automatic_seconds: float
    waiting_seconds: float


class UseCaseCost(ApiModel):
    total: CostTotals
    terminals: dict[str, CostTotals]


class UseCaseJourney(ApiModel):
    usecase: UseCase
    runs: list[RunSummary]
    summary: list[TerminalSummary]
    cost: UseCaseCost


class Verification(ApiModel):
    """A hash-chain verification (``adlc.ledger.verify.Report``)."""

    scope: str
    records_checked: int
    verified: bool
    breaks: list[dict[str, Any]]
    unscoped: list[str]
