"""Journey (feature 013, US1; SA §12.2): one lane per terminal, a bar per run coloured by its
outcome, arrows for rework, reroutes, exceptions, events and re-entry; the KPI strip; the
escalations and exceptions panel. Refreshes itself every ``ADLC_UI_DASHBOARD_REFRESH``."""

from datetime import UTC, datetime
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from adlc.config.settings import UiSettings
from adlc.ui.client import ApiClient
from adlc.ui.render import field, navigate, table

COLOURS = {
    "pass": "#2e7d32",
    "rework": "#ef6c00",
    "exception": "#6a1b9a",
    "terminate": "#c62828",
    "open": "#1565c0",
    "collapsed": "#9e9e9e",
}
ARROW_COLOURS = {
    "pass": "#bdbdbd",
    "rework": "#ef6c00",
    "reroute": "#ef6c00",
    "exception": "#6a1b9a",
}


def refresh_seconds() -> float:
    return UiSettings().ui_dashboard_refresh.total_seconds()


def render(api: ApiClient) -> None:
    st.header("Journey")
    usecases = api.get("/usecases")
    if not usecases:
        st.caption("No use cases yet.")
        return
    ids = [u["usecase_id"] for u in usecases]
    chosen = st.session_state.get("journey_usecase")
    index = ids.index(chosen) if chosen in ids else 0
    st.selectbox("Use case", ids, index=index, key="journey_usecase")
    view(api)


@st.fragment(run_every=refresh_seconds())
def view(api: ApiClient) -> None:
    usecase_id = st.session_state["journey_usecase"]
    data = api.get(f"/dashboard/usecases/{usecase_id}/journey")
    usecase = data["usecase"]
    field("Use case", f"{usecase['name']} ({usecase['status']}, risk tier {usecase['risk_tier']})")
    if data.get("time_scale", 1.0) != 1.0:
        st.caption(f"Durations are wall-clock time; timers run at scale {data['time_scale']}.")
    strip(api, usecase_id)
    st.plotly_chart(figure(data), use_container_width=True, key="journey_chart")
    panel(data["panel"])
    run_ids = [b["run_id"] for lane in data["lanes"] for b in lane["runs"] if b["run_id"]]
    if run_ids:
        pick = st.selectbox("Open run", run_ids, key="journey_open_run")
        if st.button("Open", key="journey_open"):
            navigate("Run", run_id=pick)


def strip(api: ApiClient, usecase_id: str) -> None:
    """The KPI strip: the headline KPIs; "no data" where a KPI is undefined."""
    kpis = api.get(f"/dashboard/usecases/{usecase_id}/kpis")["kpis"]
    headline = [k for k in kpis if k.get("headline")]
    columns = st.columns(max(1, len(headline)))
    for column, kpi in zip(columns, headline, strict=False):
        column.metric(kpi["name"], format_value(kpi), help=kpi["definition"])


def format_value(kpi: dict[str, Any]) -> str:
    value = kpi.get("value")
    if value is None:
        return "no data"
    unit = kpi.get("unit")
    if unit == "ratio":
        return f"{value * 100:.0f}%"
    if unit == "seconds":
        return duration(value)
    return str(value)


def duration(seconds: float) -> str:
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    parts = [
        f"{days}d" if days else "",
        f"{hours}h" if hours else "",
        f"{minutes}m" if minutes else "",
    ]
    return " ".join(p for p in parts if p) or f"{sec}s"


def _when(value: str | None) -> datetime:
    return datetime.fromisoformat(value) if value else datetime.now(UTC)


def figure(data: dict[str, Any]) -> go.Figure:
    fig = go.Figure()
    lanes = [lane["terminal_id"] for lane in data["lanes"]]
    ends: dict[str, tuple[datetime, str]] = {}
    starts: dict[str, tuple[datetime, str]] = {}
    for lane in data["lanes"]:
        for bar in lane["runs"]:
            start, end = _when(bar["opened_at"]), _when(bar["closed_at"])
            outcome = bar["final_status"] if bar["closed_at"] else "open"
            if bar.get("collapsed"):
                outcome = "collapsed"
            fig.add_trace(
                go.Bar(
                    y=[lane["terminal_id"]],
                    x=[max((end - start).total_seconds() * 1000, 1000)],
                    base=[start],
                    orientation="h",
                    marker_color=COLOURS.get(str(outcome), "#757575"),
                    name=str(outcome),
                    hovertext=(
                        f"{bar['run_id'] or bar['final_status']}<br>{outcome}"
                        f"<br>owner: {bar.get('owner') or '-'}"
                    ),
                    hoverinfo="text",
                    showlegend=False,
                )
            )
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
            arrowcolor=ARROW_COLOURS.get(arrow["kind"], "#1565c0"),
            text=arrow["kind"],
            hovertext=str(arrow.get("cause") or ""),
        )
    fig.update_layout(
        barmode="overlay",
        xaxis={"type": "date"},
        yaxis={"categoryorder": "array", "categoryarray": list(reversed(lanes))},
        height=80 + 40 * len(lanes),
        margin={"l": 40, "r": 20, "t": 20, "b": 30},
    )
    return fig


def panel(data: dict[str, Any]) -> None:
    st.subheader("Escalations and exceptions")
    if not data["escalations"] and not data["exceptions"]:
        st.caption("None.")
        return
    table(
        [
            {"run": e["run_id"], "terminal": e["terminal_id"], "trigger": e["trigger"]}
            for e in data["escalations"]
        ],
        key="journey_escalations",
    )
    table(
        [
            {"waiver": w["waiver_id"], "run": w["run_id"], "expiry": w["expiry"]}
            for w in data["exceptions"]
        ],
        key="journey_exceptions",
    )
