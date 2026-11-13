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
    "blocked": "Blocked runs",
    "dead_letter": "Dead letters",
}


def render(api: ApiClient) -> None:
    st.header("Inbox")
    st.button("Refresh", key="inbox_refresh")
    items(api)
    changes(api)


def changes(api: ApiClient) -> None:
    """012 FR-012: change requests waiting for this person's decision (ITSM owner role)."""
    found = api.get("/changes")
    if not found:
        return
    st.subheader("Change requests")
    table(
        [
            {
                "change": c["change_id"],
                "use case": c["usecase_id"],
                "summary": c.get("summary", ""),
                "window": f"{c.get('window_start', '')} to {c.get('window_end', '')}",
                "risk": c.get("risk", ""),
            }
            for c in found
        ]
    )
    ids = [c["change_id"] for c in found]
    pick = st.selectbox("Change", ids, key="change_pick")
    plan = next(c for c in found if c["change_id"] == pick).get("plan", "")
    if plan:
        st.markdown(f"**Plan**\n\n{plan}")
    decision = st.radio("Decision", ["approve", "reject"], key=f"change_decision:{pick}")
    comment = st.text_area("Comment", key=f"change_comment:{pick}")
    if st.button("Record decision", key=f"change_submit:{pick}"):
        api.post(
            f"/changes/{pick}/decision", {"approve": decision == "approve", "comment": comment}
        )
        st.success(f"{pick} {'approved' if decision == 'approve' else 'rejected'}")


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
