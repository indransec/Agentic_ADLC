"""The base of every answer model (feature 022, research R-04)."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

# A row passed through as stored (database rows, reviewer output, waiver and sign-off records):
# its keys are the store's, and values may be datetimes or decimals, serialised as before.
type Record = Annotated[
    dict[str, Any],
    Field(
        description="A record as the platform stored it (a sign-off, a clarification round, a "
        "waiver, a check, the reviewer's output…): its keys are the store's"
    ),
]
# Times arrive as datetimes from the run store and as ISO strings from JSON-stored records; each
# is serialised exactly as before (a datetime by pydantic, a string unchanged).
type Timestamp = Annotated[datetime | str, Field(description="A time, ISO 8601 in UTC")]
# Money: a decimal, serialised as a string ("0.0123").
type Money = Annotated[
    Decimal, Field(description='US dollars as a decimal string, such as "0.0125"')
]


class ApiModel(BaseModel):
    """An answer model: undeclared keys are refused (``extra="forbid"``)."""

    model_config = ConfigDict(extra="forbid")


class RunSummary(ApiModel):
    """A run at a glance (``adlc.inbox.service.run_summary``); the answer of every run action."""

    run_id: str = Field(description="`<use case>/<terminal>/run-<n>`")
    usecase_id: str
    terminal_id: str
    run_number: int
    state: str = Field(description="The run state (opened, building, awaiting_sign_off, …)")
    final_status: str | None = Field(description="The outcome once closed (pass, rework…)")
    version: int = Field(description="Send it back as `expected_version` when acting")
    controls_pending: bool = Field(description="Controls are re-running after an edit")
    opened_at: Timestamp
    closed_at: Timestamp | None
    due_at: Timestamp | None = Field(description="When the current wait is due")


class CostTotals(ApiModel):
    """Model usage and cost (``adlc.agents.cost``)."""

    calls: int
    tokens_in: int
    tokens_out: int
    cost_usd: Money | None
    unknown_cost_calls: int
    fallback_answers: int


class ErrorBody(ApiModel):
    """Every refusal (``adlc.api.errors``): a kind the client can act on, the reason in words, and
    the field it concerns when the input was invalid. Never a stack trace."""

    kind: str
    detail: str
    field: str | None = None
