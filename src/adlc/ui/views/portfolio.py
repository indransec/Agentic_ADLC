"""Portfolio (feature 013, US6): the KPIs across use cases (counts and times summed, rates pooled),
filterable by risk tier and status."""

from typing import Any

import plotly.graph_objects as go
import streamlit as st

from adlc.ui import format as fmt
from adlc.ui.client import ApiClient
from adlc.ui.render import STATUS_COLOURS, empty, page_header, table
from adlc.ui.views.journey import FONT, GRID, INK

PER_ROW = 4
# Time-split categories (the dashboard's own names) in the colours of the work they count;
# a category the platform adds later takes the next free colour
SPLIT_COLOURS = {
    "agent": STATUS_COLOURS["blue"],
    "reviewer": STATUS_COLOURS["violet"],
    "clarification": "#C9A227",
    "people": STATUS_COLOURS["orange"],
    "blocked": STATUS_COLOURS["red"],
    "other": STATUS_COLOURS["gray"],
}
SPARE_COLOURS = ["#3F8F8A", "#8C5A3C", "#5B6B8C"]
HEIGHT = 340


def any_or(value: str) -> str:
    return value.capitalize() if value else "Any"


def render(api: ApiClient) -> None:
    page_header(
        "Portfolio", "The delivery KPIs across use cases: counts and times summed, rates pooled."
    )
    with st.container(border=True):
        columns = st.columns(2)
        tier = columns[0].selectbox(
            "Risk tier", ["", "low", "medium", "high"], key="portfolio_tier", format_func=any_or
        )
        status = columns[1].selectbox(
            "Status",
            ["", "active", "closed", "terminated"],
            key="portfolio_status",
            format_func=any_or,
        )
    params = {k: v for k, v in (("risk_tier", tier), ("status", status)) if v}
    found = api.get("/dashboard/portfolio", **params)
    st.caption(f"{found['usecases']} use case(s)")
    kpis = [k for k in found["kpis"] if k["unit"] != "split"]
    for start in range(0, len(kpis), PER_ROW):
        row = st.columns(PER_ROW)
        for column, kpi in zip(row, kpis[start : start + PER_ROW], strict=False):
            column.metric(kpi["name"], fmt.kpi_value(kpi), help=kpi["definition"], border=True)
    split = next((k for k in found["kpis"] if k["id"] == "time_split"), None)
    st.subheader("Time per terminal", anchor=False)
    recorded = split and any(
        float(seconds or 0) > 0 for v in split["per_terminal"].values() for seconds in v.values()
    )
    if split and recorded:
        with st.container(border=True):
            st.plotly_chart(
                time_split(split["per_terminal"]),
                width="stretch",
                height=HEIGHT,
                key="portfolio_split_chart",
                config={"displaylogo": False},
            )
        with st.expander("Time per terminal as a table (seconds)", icon=":material/table:"):
            rows = [{"terminal": t, **v} for t, v in split["per_terminal"].items()]
            table(rows, key="portfolio_split")
    else:
        empty("No run time recorded yet.")
    with st.expander("All KPIs as a table, with their definitions", icon=":material/table:"):
        table(
            [
                {"KPI": k["name"], "value": fmt.kpi_value(k), "definition": k["definition"]}
                for k in kpis
            ],
            key="portfolio_kpis",
        )


def time_split(per_terminal: dict[str, dict[str, Any]]) -> go.Figure:
    """Hours per terminal, stacked by category (automatic work, waiting for people)."""
    terminals = list(per_terminal)
    categories = list(dict.fromkeys(c for v in per_terminal.values() for c in v))
    fig = go.Figure()
    spare = iter(SPARE_COLOURS * len(categories))
    for category in categories:
        seconds = [float(per_terminal[t].get(category) or 0) for t in terminals]
        fig.add_trace(
            go.Bar(
                x=terminals,
                y=[s / 3600 for s in seconds],
                name=fmt.label(category),
                marker={
                    "color": SPLIT_COLOURS.get(category) or next(spare),
                    "line": {"width": 0},
                },
                hovertext=[
                    f"{t}: {fmt.duration(s)}" for t, s in zip(terminals, seconds, strict=True)
                ],
                hoverinfo="text+name",
            )
        )
    fig.update_layout(
        template="plotly_white",
        barmode="stack",
        bargap=0.4,
        font={"family": FONT, "color": INK, "size": 12},
        yaxis={"title": "hours", "gridcolor": GRID, "rangemode": "tozero"},
        xaxis={"title": None},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0, "title": None},
        height=HEIGHT,
        margin={"l": 8, "r": 8, "t": 36, "b": 8},
    )
    return fig
