"""Journey (feature 013, US1; SA §12.2): one lane per terminal, a bar per run coloured by its
outcome, arrows for rework, reroutes, exceptions, events and re-entry; the KPI strip; the
escalations and exceptions panel. Refreshes itself every ``ADLC_UI_DASHBOARD_REFRESH``."""

from datetime import UTC, datetime
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from adlc.config.settings import UiSettings
from adlc.ui import format as fmt
from adlc.ui.client import ApiClient
from adlc.ui.render import (
    STATUS_COLOURS,
    empty,
    field,
    navigate,
    open_picker,
    page_header,
    status_badge,
    status_colour,
    status_text,
    table,
)

# Kept here for the pages and tests that format KPI values and durations through this module
duration = fmt.duration
format_value = fmt.kpi_value
ARROW_COLOURS = {
    "rework": STATUS_COLOURS["orange"],
    "reroute": STATUS_COLOURS["orange"],
    "exception": STATUS_COLOURS["violet"],
}
OUTCOME_NAMES = {"open": "In progress", "collapsed": "Collapsed"}
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
GRID = "#E4E8EE"
INK = "#1B2430"
MUTED = "#6B7588"


def refresh_seconds() -> float:
    return UiSettings().ui_dashboard_refresh.total_seconds()


def render(api: ApiClient) -> None:
    page_header(
        "Journey",
        "Each terminal's runs over time, coloured by outcome, with reworks and reroutes drawn "
        "between them.",
    )
    usecases = api.get("/usecases")
    if not usecases:
        empty("No use cases yet.")
        return
    ids = [u["usecase_id"] for u in usecases]
    if (pick := st.session_state.pop("journey_pick", None)) in ids:
        st.session_state["journey_usecase"] = pick  # opened from a use case
    chosen = st.session_state.get("journey_usecase")
    index = ids.index(chosen) if chosen in ids else 0
    st.selectbox("Use case", ids, index=index, key="journey_usecase")
    view(api)


@st.fragment(run_every=refresh_seconds())
def view(api: ApiClient) -> None:
    usecase_id = st.session_state["journey_usecase"]
    data = api.get(f"/dashboard/usecases/{usecase_id}/journey")
    usecase = data["usecase"]
    with st.container(border=True):
        name, status, risk = st.columns([4, 2, 2])
        with name:
            field("Use case", usecase["name"])
        with status:
            st.caption("Status")
            status_badge(usecase["status"])
        with risk:
            st.caption("Risk tier")
            status_badge(usecase["risk_tier"])
    if data.get("time_scale", 1.0) != 1.0:
        st.caption(f"Durations are wall-clock time; timers run at scale {data['time_scale']}.")
    strip(api, usecase_id)
    chart = figure(data)
    with st.container(border=True):
        st.plotly_chart(
            chart,
            width="stretch",
            height=int(chart.layout.height),
            key="journey_chart",
            config={"displaylogo": False},
        )
    panel(data["panel"])
    run_ids = [b["run_id"] for lane in data["lanes"] for b in lane["runs"] if b["run_id"]]
    if pick := open_picker(
        run_ids, select_key="journey_open_run", button_key="journey_open", label="Run"
    ):
        navigate("Run", run_id=pick)


def strip(api: ApiClient, usecase_id: str) -> None:
    """The KPI strip: the headline KPIs; "no data" where a KPI is undefined."""
    kpis = api.get(f"/dashboard/usecases/{usecase_id}/kpis")["kpis"]
    headline = [k for k in kpis if k.get("headline")]
    columns = st.columns(max(1, len(headline)))
    for column, kpi in zip(columns, headline, strict=False):
        column.metric(kpi["name"], format_value(kpi), help=kpi["definition"], border=True)


def _when(value: str | None) -> datetime:
    return datetime.fromisoformat(value) if value else datetime.now(UTC)


def outcome_of(bar: dict[str, Any]) -> str:
    if bar.get("collapsed"):
        return "collapsed"
    return str(bar["final_status"]) if bar["closed_at"] else "open"


def outcome_name(outcome: str) -> str:
    return OUTCOME_NAMES.get(outcome) or status_text(outcome)


def outcome_colour(outcome: str) -> str:
    if outcome == "open":
        return STATUS_COLOURS["blue"]
    return status_colour(outcome)


def figure(data: dict[str, Any]) -> go.Figure:
    fig = go.Figure()
    lanes = [lane["terminal_id"] for lane in data["lanes"]]
    ends: dict[str, tuple[datetime, str]] = {}
    starts: dict[str, tuple[datetime, str]] = {}
    legend: set[str] = set()
    opened = [_when(b["opened_at"]) for lane in data["lanes"] for b in lane["runs"]]
    if lanes:  # every terminal's lane, including those no run has reached yet
        fig.add_trace(
            go.Scatter(
                y=lanes,
                x=[min(opened, default=datetime.now(UTC))] * len(lanes),
                mode="markers",
                marker={"opacity": 0},
                hoverinfo="skip",
                showlegend=False,
            )
        )
    for lane in data["lanes"]:
        for bar in lane["runs"]:
            start, end = _when(bar["opened_at"]), _when(bar["closed_at"])
            outcome = outcome_of(bar)
            fig.add_trace(
                go.Bar(
                    y=[lane["terminal_id"]],
                    x=[max((end - start).total_seconds() * 1000, 1000)],
                    base=[start],
                    orientation="h",
                    marker={"color": outcome_colour(outcome), "line": {"width": 0}},
                    name=outcome_name(outcome),
                    legendgroup=outcome,
                    showlegend=outcome not in legend,
                    hovertext=(
                        f"{bar['run_id'] or bar['final_status']}<br>{outcome_name(outcome)}"
                        f"<br>owner: {bar.get('owner') or '-'}"
                    ),
                    hoverinfo="text",
                )
            )
            legend.add(outcome)
            if bar["run_id"]:
                starts[bar["run_id"]] = (start, lane["terminal_id"])
                ends[bar["run_id"]] = (end, lane["terminal_id"])
    for arrow in data["arrows"]:
        if (
            arrow["kind"] == "pass"
            or arrow["from_run"] not in ends
            or arrow["to_run"] not in starts
        ):
            continue  # plain passes follow the lane order; only reroutes and the like are drawn
        (x0, y0), (x1, y1) = ends[arrow["from_run"]], starts[arrow["to_run"]]
        colour = ARROW_COLOURS.get(arrow["kind"], STATUS_COLOURS["blue"])
        fig.add_annotation(
            x=x1,
            y=y1,
            ax=x0,
            ay=y0,
            xref="x",
            yref="y",
            axref="x",
            ayref="y",
            showarrow=True,
            arrowhead=3,
            arrowwidth=1.5,
            arrowcolor=colour,
            text=arrow["kind"],
            font={"color": colour, "size": 11},
            hovertext=str(arrow.get("cause") or ""),
        )
    fig.update_layout(
        template="plotly_white",
        barmode="overlay",
        bargap=0.35,
        font={"family": FONT, "color": INK, "size": 12},
        xaxis={"type": "date", "gridcolor": GRID, "title": None, "tickfont": {"color": MUTED}},
        yaxis={
            "categoryorder": "array",
            "categoryarray": list(reversed(lanes)),
            "title": None,
            "gridcolor": GRID,
        },
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0, "title": None},
        height=110 + 44 * len(lanes),
        margin={"l": 8, "r": 8, "t": 36, "b": 8},
        hoverlabel={"font": {"family": FONT}},
    )
    return fig


def panel(data: dict[str, Any]) -> None:
    st.subheader("Escalations and exceptions", anchor=False)
    if data.get("unlinked"):
        st.caption("Runs opened by an event whose source run is unknown:")
        table(data["unlinked"], key="journey_unlinked")
    if not data["escalations"] and not data["exceptions"]:
        empty("No escalations or exceptions on this use case.")
        return
    escalations, exceptions = st.columns(2)
    with escalations:
        st.caption("Escalations")
        table(
            [
                {"run": e["run_id"], "terminal": e["terminal_id"], "trigger": e["trigger"]}
                for e in data["escalations"]
            ],
            key="journey_escalations",
        )
    with exceptions:
        st.caption("Exceptions (waivers)")
        table(
            [
                {"waiver": w["waiver_id"], "run": w["run_id"], "expiry": w["expiry"]}
                for w in data["exceptions"]
            ],
            key="journey_exceptions",
        )
