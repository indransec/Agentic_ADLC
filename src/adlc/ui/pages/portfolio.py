"""Portfolio (feature 013, US6): the KPIs across use cases (counts and times summed, rates pooled),
filterable by risk tier and status."""

import streamlit as st

from adlc.ui.client import ApiClient
from adlc.ui.pages.journey import format_value
from adlc.ui.render import table


def render(api: ApiClient) -> None:
    st.header("Portfolio")
    columns = st.columns(2)
    tier = columns[0].selectbox("Risk tier", ["", "low", "medium", "high"], key="portfolio_tier")
    status = columns[1].selectbox(
        "Status", ["", "active", "closed", "terminated"], key="portfolio_status"
    )
    params = {k: v for k, v in (("risk_tier", tier), ("status", status)) if v}
    found = api.get("/dashboard/portfolio", **params)
    st.caption(f"{found['usecases']} use case(s)")
    table(
        [
            {"KPI": k["name"], "value": format_value(k), "definition": k["definition"]}
            for k in found["kpis"]
            if k["unit"] != "split"
        ],
        key="portfolio_kpis",
    )
    split = next((k for k in found["kpis"] if k["id"] == "time_split"), None)
    if split and split["per_terminal"]:
        st.subheader("Time per terminal (seconds)")
        rows = [{"terminal": t, **v} for t, v in split["per_terminal"].items()]
        table(rows, key="portfolio_split")
