"""013 T023 (US1-US6; FR-007; SC-003): the dashboard pages through the API."""

import pytest
from sqlalchemy import text

from adlc.ui.pages import journey
from tests.support.api import Api
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness
from tests.support.ui import frame, go, open_ui, sign_in


def test_journey_page_draws_lanes_strip_and_panel(h: Harness, api: Api) -> None:
    usecase, _ = walk_to(h, "T3")
    at = go(sign_in(open_ui(api), "sre"), "Journey")
    assert not at.exception, at.exception
    assert at.selectbox(key="journey_usecase").value == usecase
    metrics = {m.label: m.value for m in at.metric}
    assert "Reworks" in metrics and metrics["Escalations"] == "0"
    assert metrics["SLA adherence"] in ("no data",) or metrics["SLA adherence"].endswith("%")
    assert "Escalations and exceptions" in [s.value for s in at.subheader]
    assert len(at.get("plotly_chart")) == 1


def test_refresh_follows_the_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADLC_UI_DASHBOARD_REFRESH", "7s")
    assert journey.refresh_seconds() == 7.0  # SC-003: the fragments refresh at this interval
    assert journey.duration(3725) == "1h 2m" and journey.duration(42) == "42s"


def test_activity_filters_survive_a_refresh(h: Harness, api: Api) -> None:
    usecase, _ = walk_to(h, "T2")
    at = go(sign_in(open_ui(api), "sre"), "Activity")
    at.selectbox(key="activity_usecase").set_value(usecase)
    at.selectbox(key="activity_actor").set_value("human")
    at = at.run()
    feed = frame(at, "actor_type")
    assert set(feed["actor_type"]) == {"human"}
    at = at.run()  # a refresh keeps the filters
    assert at.selectbox(key="activity_actor").value == "human"
    assert set(frame(at, "actor_type")["actor_type"]) == {"human"}


def test_portfolio_page(h: Harness, api: Api) -> None:
    walk_to(h, "T2")
    walk_to(h, "T1", tier="low")
    at = go(sign_in(open_ui(api), "adlc_coe"), "Portfolio")
    assert not at.exception, at.exception
    assert "2 use case(s)" in [c.value for c in at.caption]
    kpis = frame(at, "KPI")
    assert "First-pass yield" in set(kpis["KPI"])
    at.selectbox(key="portfolio_tier").set_value("low")
    at = at.run()
    assert "1 use case(s)" in [c.value for c in at.caption]


def test_dead_letter_payload_for_the_coe(h: Harness, api: Api) -> None:
    h.submit()
    with h.owner.begin() as conn:
        conn.execute(
            text(
                "UPDATE events.outbox_event SET dead_lettered_at = now(), last_error = 'x' "
                "WHERE event_type = 'usecase.submitted'"
            )
        )
    at = go(sign_in(open_ui(api), "adlc_coe"), "Dead letters")
    at.button(key="dead_detail").click()
    at = at.run()
    assert not at.exception, at.exception
    assert len(at.json) == 1
