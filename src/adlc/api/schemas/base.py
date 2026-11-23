"""The base of every answer model (feature 022, research R-04)."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

# A row passed through as stored (database rows, reviewer output, waiver and sign-off records):
# its keys are the store's, and values may be datetimes or decimals, serialised as before.
type Record = dict[str, Any]
# Times arrive as datetimes from the run store and as ISO strings from JSON-stored records; each
# is serialised exactly as before (a datetime by pydantic, a string unchanged).
type Timestamp = datetime | str
# Money: a decimal, serialised as a string ("0.0123").
type Money = Decimal


class ApiModel(BaseModel):
    """An answer model: undeclared keys are refused (``extra="forbid"``)."""

    model_config = ConfigDict(extra="forbid")


class RunSummary(ApiModel):
    """A run at a glance (``adlc.inbox.service.run_summary``); the answer of every run action."""

    run_id: str
    usecase_id: str
    terminal_id: str
    run_number: int
    state: str
    final_status: str | None
    version: int
    controls_pending: bool
    opened_at: Timestamp
    closed_at: Timestamp | None
    due_at: Timestamp | None


class CostTotals(ApiModel):
    """Model usage and cost (``adlc.agents.cost``)."""

    calls: int
    tokens_in: int
    tokens_out: int
    cost_usd: Money | None
    unknown_cost_calls: int
    fallback_answers: int
