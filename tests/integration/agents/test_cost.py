"""T034: cost views, alerts and complete call records (US5; FR-021, FR-022; SC-001, SC-007)."""

from decimal import Decimal
from typing import Any

import pytest

from adlc.agents.cost import CostAlerts, alerts, run_cost, terminal_cost, usecase_cost
from adlc.agents.fake import FakeGateway, reply
from adlc.agents.store import SqlCallRecorder
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, harness
from tests.support.pg import PlatformDatabase

from .test_reviewer import _items, _review
from .test_runtime import MODELS, PRIMARY


@pytest.fixture
def priced(orch_template: PlatformDatabase) -> Any:
    opened: list[Any] = []

    def make(tokens: tuple[int, int], levels: list[Decimal]) -> tuple[Harness, FakeGateway]:
        class Late:
            gateway: FakeGateway | None = None

            def complete(self, request: Any) -> Any:
                assert self.gateway is not None
                return self.gateway.complete(request)

        late = Late()
        ctx = harness(orch_template, gateway=late, reviewer_mode="model")
        h = ctx.__enter__()
        opened.append(ctx)
        gateway = FakeGateway(
            MODELS,
            {PRIMARY: lambda m: reply(_review("pass", None, _items(m)), tokens=tokens)},
            recorder=SqlCallRecorder(h.app),
        )
        gateway.after_record = CostAlerts(h.app, levels).check
        late.gateway = gateway
        return h, gateway

    yield make
    for ctx in opened:
        ctx.__exit__(None, None, None)


def test_every_call_of_a_full_walk_is_recorded(priced: Any) -> None:
    """SC-001: one complete call record per gateway request over the walk.

    T7's data ceiling is the resolver ``per_T2_prod_design``, which no model is approved for
    until it is resolved (R-16: fails closed), so its model review escalates with
    reviewer_failed and records only skipped entries."""
    h, gateway = priced((1000, 200), [])
    usecase, t7 = walk_to(h, "T7")
    t7_run = h.run(t7)
    assert (t7_run.state, t7_run.escalation_trigger) == ("escalated", "reviewer_failed")
    rows = h.sql(
        "SELECT provider, model, tokens_in, tokens_out, cost_usd, cost_known, outcome "
        "FROM run.model_call WHERE usecase_id = :u",
        u=usecase,
    )
    requests = [r for r in rows if r[6] != "skipped"]
    assert len(requests) == len(gateway.fake.calls) == 7  # T0 to T6, one review each
    assert all(r[0] and r[1] and r[2] == 1000 and r[3] == 200 and r[5] for r in requests)
    skipped = h.sql("SELECT DISTINCT reason FROM run.model_call WHERE run_id = :r", r=t7)
    assert [s[0] for s in skipped] == ["data_class"]
    # Opus prices: 1000 x $4 + 200 x $20 per million tokens = $0.008 per call.
    total = usecase_cost(h.app, usecase)
    assert total["calls"] == 7 and total["cost_usd"] == Decimal("0.008000") * 7
    assert total["unknown_cost_calls"] == 0 and total["fallback_answers"] == 0


def test_views_add_up_to_the_calls(priced: Any) -> None:
    """SC-007: per run, terminal and use case, to the cent."""
    h, _ = priced((2000, 500), [])
    usecase, t2 = walk_to(h, "T2")
    t1 = h.sql(
        "SELECT run_id FROM run.terminal_run WHERE usecase_id = :u AND terminal_id = 'T1'",
        u=usecase,
    )[0][0]
    calls = h.sql("SELECT cost_usd FROM run.model_call WHERE run_id = :r", r=t1)
    assert run_cost(h.app, t1)["cost_usd"] == sum(c[0] for c in calls)
    assert terminal_cost(h.app, usecase, "T1")["cost_usd"] == run_cost(h.app, t1)["cost_usd"]
    by_terminal = sum(terminal_cost(h.app, usecase, t)["cost_usd"] for t in ("T0", "T1", "T2"))
    assert usecase_cost(h.app, usecase)["cost_usd"] == by_terminal


def test_alert_levels_fire_once_each(priced: Any) -> None:
    # $4 + $2 = $6 per review: 5 is crossed at T0, 20 at T3.
    h, _ = priced((1_000_000, 100_000), [Decimal(5), Decimal(20)])
    usecase, _ = walk_to(h, "T4")
    rows = alerts(h.app, usecase)
    assert [r["level_usd"] for r in rows] == [Decimal("5.00"), Decimal("20.00")]
    assert rows[0]["total_usd"] == Decimal("6.000000") and rows[1]["total_usd"] == Decimal(
        "24.000000"
    )
    assert (
        h.run(h.active(usecase, "T4").run_id).state == "awaiting_sign_off"
    )  # alerts never stop runs
