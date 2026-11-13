"""013 T019 (US6; FR-010): portfolio KPIs pool the records (never a mean of rates)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from adlc.dashboard.kpis import Records, RunFact, SignOff, compute, pool

T0 = datetime(2026, 11, 13, 9, tzinfo=UTC)


def usecase(n: str, firsts: list[str], reworks: int, minutes: float) -> Records:
    runs = [
        RunFact(f"{n}/T{i}/run-1", f"T{i}", 1, status, T0, T0 + timedelta(minutes=5))
        for i, status in enumerate(firsts)
    ]
    signs = [SignOff(f"{n}/T0/run-1", "rework", "requirement") for _ in range(reworks)]
    return Records(T0, None, T0 + timedelta(minutes=minutes), runs, {}, signs, (), (), (), ())


def by_id(kpis: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {k["id"]: k for k in kpis}


def test_counts_sum_and_rates_pool() -> None:
    a = usecase("UC-1", ["pass"], 1, 60)  # yield 1/1
    b = usecase("UC-2", ["rework", "rework", "rework", "pass"], 2, 120)  # yield 1/4
    found = by_id(pool([a, b], T0 + timedelta(hours=3)))
    assert found["reworks"]["value"] == 3
    assert found["first_pass_yield"]["value"] == pytest.approx(2 / 5)  # pooled, not (1 + 0.25) / 2
    assert found["elapsed"]["value"] == pytest.approx(90 * 60)  # mean per use case
    assert by_id(compute(a))["first_pass_yield"]["value"] == 1.0


def test_no_use_cases() -> None:
    found = by_id(pool([], T0))
    assert found["elapsed"]["value"] is None and found["first_pass_yield"]["value"] is None
