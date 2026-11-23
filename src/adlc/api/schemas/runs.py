"""Answers of ``/runs/{run_id}`` (the run detail, SA §8.2) and the run decisions."""

from typing import Any

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

    outcomes: list[str]
    requires: dict[str, list[str]]
    root_causes: list[str]
    target_terminal_for: list[str]
    target_terminals: list[str]
    typed_fields: list[str]
    alternatives: list[str]
    reason_required_unless: str | None
    sign_off_role: str | None
    can_decide: bool
    can_terminate: bool
    can_edit: bool
    can_complete_escalation: bool
    controls_pending: bool
    waiver_pending: bool


class RunDetail(ApiModel):
    run: RunSummary
    spec: SpecRef
    artifacts: list[RunArtifact]
    prerequisites: list[Record]
    control_results: list[Record]
    recommendation: Record | None
    prior_rework: list[PriorRework]
    clarifications: list[Record]
    approvals: list[Approval]
    decisions: list[Record]
    waiver: Record | None
    timer: Timer
    cost: CostTotals
    timeline: list[Record]
    checks: list[Record]
    checklist_results: list[Record]
    ledger_record: Record | None
    form: DecisionForm
