"""022 T011 (research R-04): an answer model refuses keys it does not declare, so a service
that starts returning a new key fails in the tests instead of the key being silently dropped."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from adlc.api.schemas.base import CostTotals, RunSummary

RUN = {
    "run_id": "UC-0001/T1/run-1",
    "usecase_id": "UC-0001",
    "terminal_id": "T1",
    "run_number": 1,
    "state": "awaiting_sign_off",
    "final_status": None,
    "version": 3,
    "controls_pending": False,
    "opened_at": datetime(2026, 11, 23, 9, 0, tzinfo=UTC),
    "closed_at": None,
    "due_at": "2026-11-30T09:00:00+00:00",
}


def test_an_undeclared_key_is_refused() -> None:
    with pytest.raises(ValidationError, match="extra"):
        RunSummary.model_validate({**RUN, "secret_internal": 1})


def test_times_keep_their_form() -> None:
    dumped = RunSummary.model_validate(RUN).model_dump(mode="json")
    assert dumped["opened_at"] == "2026-11-23T09:00:00Z"  # a datetime, as pydantic writes it
    assert dumped["due_at"] == "2026-11-30T09:00:00+00:00"  # a stored string, unchanged


def test_money_is_a_decimal_string() -> None:
    totals = CostTotals(
        calls=1,
        tokens_in=2,
        tokens_out=3,
        cost_usd=Decimal("0.0125"),
        unknown_cost_calls=0,
        fallback_answers=0,
    )
    assert totals.model_dump(mode="json")["cost_usd"] == "0.0125"
