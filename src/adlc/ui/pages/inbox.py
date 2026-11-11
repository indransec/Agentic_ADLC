"""Inbox: everything waiting for the signed-in person (FR-006, FR-007).

Refreshes itself every 30 seconds and on demand (research R-09).
"""

from typing import Any

import streamlit as st

from adlc.ui.client import ApiClient
from adlc.ui.render import navigate, table

REFRESH_SECONDS = 30
KIND_TITLES = {
    "sign_off": "Sign-offs",
    "clarification": "Clarifications",
    "escalation": "Escalations",
    "waiver": "Waivers",
    "dead_letter": "Dead letters",
}


def render(api: ApiClient) -> None:
    st.header("Inbox")
    st.button("Refresh", key="inbox_refresh")
    items(api)


@st.fragment(run_every=REFRESH_SECONDS)
def items(api: ApiClient) -> None:
    found = api.get("/inbox")
    if not found:
        st.caption("Nothing is waiting for you.")
    for kind in dict.fromkeys(i["kind"] for i in found):  # kinds in order of their first item
        st.subheader(KIND_TITLES.get(kind, kind.replace("_", " ").capitalize()))
        table(
            [
                {
                    "title": i["title"],
                    "use case": i["usecase_id"],
                    "terminal": i["terminal_id"],
                    "as role": i["role"],
                    "arrived": i["arrived_at"],
                    "due": i["due_at"],
                    "note": "controls being re-run" if i["controls_pending"] else "",
                }
                for i in found
                if i["kind"] == kind
            ]
        )
    if not found:
        return
    labels = {f"{i['kind'].replace('_', ' ')}: {i['title']} ({i['id']})": i for i in found}
    pick = st.selectbox("Open", list(labels), key="inbox_pick")
    if st.button("Open", key="inbox_open"):
        open_item(labels[pick])


def open_item(item: dict[str, Any]) -> None:
    kind = item["kind"]
    if kind == "clarification":
        navigate("Clarification", run_id=item["run_id"], clarification_id=item["id"])
    elif kind == "waiver":
        navigate("Waiver", run_id=item["run_id"], waiver_id=item["id"])
    elif kind == "escalation":
        navigate("Escalation", run_id=item["run_id"])
    elif kind == "dead_letter":
        navigate("Dead letters")
    else:
        navigate("Run", run_id=item["run_id"])
