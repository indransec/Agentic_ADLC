"""Answers of ``/dashboard`` (feature 013): journey, KPIs, portfolio, activity, run timeline."""

from typing import Any

from adlc.api.schemas.base import ApiModel, Record


class JourneyUseCase(ApiModel):
    usecase_id: str
    name: str
    risk_tier: str | None
    status: str


class LaneBar(ApiModel):
    """A run in a lane, or several earlier runs collapsed into one bar (``collapsed`` set)."""

    run_id: str | None
    terminal_id: str
    run_number: int
    state: str
    final_status: str | None
    mode: str | None = None  # absent on a collapsed bar
    opened_at: str | None
    closed_at: str | None
    seconds: float
    owner: str | None
    time_split: dict[str, float]
    collapsed: int | None = None  # only on a collapsed bar


class Lane(ApiModel):
    terminal_id: str
    name: str
    runs: list[LaneBar]


class Arrow(ApiModel):
    from_run: str
    to_run: str
    kind: str
    event_type: str
    cause: dict[str, Any]
    actor: str | None
    at: str | None


class PanelEscalation(ApiModel):
    run_id: str
    terminal_id: str
    trigger: str | None


class PanelUnlinked(ApiModel):
    run_id: str
    event_type: str


class Panel(ApiModel):
    escalations: list[PanelEscalation]
    exceptions: list[Record]
    unlinked: list[PanelUnlinked]


class Journey(ApiModel):
    usecase: JourneyUseCase
    lanes: list[Lane]
    arrows: list[Arrow]
    panel: Panel
    time_scale: float


class Kpi(ApiModel):
    """One KPI (``adlc.dashboard.kpis``); its value's form depends on the KPI (a number, a
    breakdown or nothing yet), and some KPIs add a per-terminal split, details or a note."""

    id: str
    name: str
    unit: str
    headline: bool
    definition: str
    value: Any
    per_terminal: Any = None
    detail: Any = None
    definition_note: str | None = None


class Kpis(ApiModel):
    kpis: list[Kpi]


class Portfolio(ApiModel):
    usecases: int
    kpis: list[Kpi]


class ActivityEntry(ApiModel):
    at: str | None
    usecase_id: str
    run_id: str
    terminal_id: str
    actor_type: str
    actor: str
    step: str
    outcome: str | None
    seconds: float


class TimelineActivity(ApiModel):
    at: str | None
    step: str
    actor_type: str
    actor: str
    outcome: str | None
    seconds: float


class AgentAttempt(ApiModel):
    kind: str
    attempt: int
    agent_id: str
    implementation: str
    steps: int | None
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: float | None
    model_calls: list[Record]
    tool_calls: list[Record]


class RunTimeline(ApiModel):
    run_id: str
    activity: list[TimelineActivity]
    attempts: list[AgentAttempt]
