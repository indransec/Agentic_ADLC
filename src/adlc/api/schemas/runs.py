"""Answers of ``/runs/{run_id}`` (the run detail, SA §8.2) and the run decisions."""

from typing import Any

from pydantic import Field

from adlc.api.schemas.base import ApiModel, CostTotals, Record, RunSummary, Timestamp


class SpecRef(ApiModel):
    terminal_id: str
    version: str


class ArtifactVersion(ApiModel):
    version: int
    producer_type: str
    producer_id: str
    schema_valid: bool
    created_at: Timestamp


class RunArtifact(ApiModel):
    """One artifact of the terminal: its rows as stored (a table, text or nothing yet)."""

    id: str
    columns: list[str]
    condition: Any
    rows: Any
    version: ArtifactVersion | None
    attachments: list[Record]
    citations: list[Record]


class PriorRework(ApiModel):
    run_id: str
    person: str
    signed_at: Timestamp
    comment: str | None
    root_cause: str | None


class Approval(ApiModel):
    person: str
    role: str
    signed_at: Timestamp


class Timer(ApiModel):
    due_at: Timestamp | None
    overdue: bool


class DecisionForm(ApiModel):
    """What this person may decide and what each outcome needs (``adlc.inbox.forms``).

    Every value comes from the pinned spec and catalogues, so none is a literal here.
    """

    outcomes: list[str] = Field(description="What this person may decide now")
    requires: dict[str, list[str]] = Field(description="Per outcome, the fields it needs")
    root_causes: list[str] = Field(description="Rework root causes to choose from")
    target_terminal_for: list[str] = Field(
        description="Root causes that also need `target_terminal`"
    )
    target_terminals: list[str] = Field(description="The use case's pinned terminals")
    typed_fields: list[str] = Field(description="Values a pass needs the person to type")
    alternatives: list[str] = Field(description="Alternative routes a pass may take")
    reason_required_unless: str | None = Field(
        description="The reviewer's recommendation: any other decision needs a `reason`"
    )
    sign_off_role: str | None = Field(description="The role this person signs under")
    can_decide: bool = Field(
        description="May decide now (not while controls re-run or a waiver is pending)"
    )
    can_terminate: bool = Field(description="May terminate the run")
    can_edit: bool = Field(description="May edit the artifacts")
    can_complete_escalation: bool = Field(description="May complete the escalation")
    controls_pending: bool = Field(description="Controls are re-running after an edit")
    waiver_pending: bool = Field(description="A waiver awaits its approver")


class RunDetail(ApiModel):
    run: RunSummary = Field(description="The run at a glance")
    spec: SpecRef = Field(description="The pinned terminal spec")
    artifacts: list[RunArtifact] = Field(description="Every artifact the spec declares")
    prerequisites: list[Record] = Field(
        description="Each prerequisite with its latest result and reason"
    )
    control_results: list[Record] = Field(description="The controls' latest results")
    recommendation: Record | None = Field(
        description="The reviewer agent's recommendation, with its checklist `items`"
    )
    prior_rework: list[PriorRework] = Field(
        description="Earlier runs of this terminal sent to rework, newest first"
    )
    clarifications: list[Record] = Field(description="Clarification rounds of this run")
    approvals: list[Approval] = Field(description="Passes recorded so far")
    decisions: list[Record] = Field(description="Every sign-off decision on this run")
    waiver: Record | None = Field(description="The pending waiver, if any")
    timer: Timer = Field(description="When the run is due, and whether it is overdue")
    cost: CostTotals = Field(description="Model usage and cost of this run")
    timeline: list[Record] = Field(description="The run's steps (`run_activity`)")
    checks: list[Record] = Field(description="The policy engine's decisions")
    checklist_results: list[Record] = Field(description="The checklist scores recorded")
    ledger_record: Record | None = Field(
        description="The evidence ledger record, once the run closed"
    )
    form: DecisionForm = Field(description="What this person may decide and what it needs")
