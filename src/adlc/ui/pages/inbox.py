"""Inbox: everything waiting for the signed-in person (FR-006, FR-007).

Refreshes itself every 30 seconds and on demand (research R-09).
"""

import streamlit as st

from adlc.ui.client import ApiClient
from adlc.ui.render import navigate, table

REFRESH_SECONDS = 30


def render(api: ApiClient) -> None:
    st.header("Inbox")
    st.button("Refresh", key="inbox_refresh")
    items(api)


@st.fragment(run_every=REFRESH_SECONDS)
def items(api: ApiClient) -> None:
    found = api.get("/inbox")
    table(
        [
            {
                "kind": i["kind"].replace("_", " "),
                "title": i["title"],
                "use case": i["usecase_id"],
                "terminal": i["terminal_id"],
                "as role": i["role"],
                "arrived": i["arrived_at"],
                "due": i["due_at"],
            }
            for i in found
        ]
    )
    runs = [i["run_id"] for i in found if i.get("run_id")]
    if not runs:
        return
    pick = st.selectbox("Open", runs, key="inbox_pick")
    if st.button("Open run", key="inbox_open"):
        navigate("Run", run_id=pick)
