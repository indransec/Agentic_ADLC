"""Inbox: everything waiting for the signed-in person (FR-006, FR-007).

Refreshes itself every 30 seconds and on demand (research R-09).
"""

from datetime import UTC, datetime
from typing import Any

import streamlit as st

from adlc.ui import format as fmt
from adlc.ui.client import ApiClient
from adlc.ui.render import empty, navigate, open_picker, page_header, table

REFRESH_SECONDS = 30
KIND_TITLES = {
    "sign_off": "Sign-offs",
    "clarification": "Clarifications",
    "escalation": "Escalations",
    "waiver": "Waivers",
    "blocked": "Blocked runs",
    "dead_letter": "Dead letters",
}


def kind_title(kind: str) -> str:
    return KIND_TITLES.get(kind, kind.replace("_", " ").capitalize())


def render(api: ApiClient) -> None:
    title, refresh = st.columns([5, 1], vertical_alignment="bottom")
    with title:
        page_header("Inbox", "Decisions and requests waiting for you, oldest first.")
    refresh.button("Refresh", key="inbox_refresh", icon=":material/refresh:", width="stretch")
    items(api)
    changes(api)
    proposed_events(api)


def changes(api: ApiClient) -> None:
    """012 FR-012: change requests waiting for this person's decision (ITSM owner role)."""
    found = api.get("/changes")
    if not found:
        return
    st.subheader("Change requests", anchor=False)
    table(
        [
            {
                "change": c["change_id"],
                "use case": c["usecase_id"],
                "summary": c.get("summary", ""),
                "window": f"{fmt.when(c.get('window_start'))} to {fmt.when(c.get('window_end'))}",
                "risk": c.get("risk", ""),
            }
            for c in found
        ]
    )
    with st.container(border=True):
        ids = [c["change_id"] for c in found]
        pick = st.selectbox("Change", ids, key="change_pick")
        plan = next(c for c in found if c["change_id"] == pick).get("plan", "")
        if plan:
            st.caption("Plan")
            st.text(str(plan))  # written by an agent: plain text
        decision = st.radio(
            "Decision", ["approve", "reject"], key=f"change_decision:{pick}", horizontal=True
        )
        comment = st.text_area("Comment", key=f"change_comment:{pick}")
        if st.button("Record decision", key=f"change_submit:{pick}", type="primary"):
            api.post(
                f"/changes/{pick}/decision", {"approve": decision == "approve", "comment": comment}
            )
            st.success(f"{pick} {'approved' if decision == 'approve' else 'rejected'}")


@st.fragment(run_every=REFRESH_SECONDS)
def items(api: ApiClient) -> None:
    found = api.get("/inbox")
    now = datetime.now(UTC)
    st.caption(f":material/schedule: Updated {now.strftime('%H:%M:%S')} UTC")
    if not found:
        with st.container(border=True):
            empty("Nothing is waiting for you.")
        return
    kinds = list(dict.fromkeys(i["kind"] for i in found))  # in order of their first item
    overdue = [i for i in found if (due := fmt.parse_time(i.get("due_at"))) and due < now]
    columns = st.columns(len(kinds) + 1)
    columns[0].metric("Waiting", len(found), border=True)
    for column, kind in zip(columns[1:], kinds, strict=True):
        count = sum(1 for i in found if i["kind"] == kind)
        late = sum(1 for i in overdue if i["kind"] == kind)
        column.metric(
            kind_title(kind),
            count,
            delta=f"{late} overdue" if late else None,
            delta_color="inverse",
            delta_arrow="off",
            border=True,
        )
    for kind in kinds:
        st.subheader(kind_title(kind), anchor=False)
        table(
            [
                {
                    "title": i["title"],
                    "use case": i["usecase_id"],
                    "terminal": i["terminal_id"],
                    "as role": str(i["role"]).replace("_", " "),
                    "arrived": i["arrived_at"],
                    "due": i["due_at"],
                    "overdue": "overdue" if i in overdue else "",
                    "note": "controls being re-run" if i["controls_pending"] else "",
                }
                for i in found
                if i["kind"] == kind
            ],
            key=f"inbox_table:{kind}",
        )
    labels = {f"{i['kind'].replace('_', ' ')}: {i['title']} ({i['id']})": i for i in found}
    if pick := open_picker(list(labels), select_key="inbox_pick", button_key="inbox_open"):
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


def proposed_events(api: ApiClient) -> None:
    """012 FR-007: lifecycle events an agent proposed; confirming raises the event."""
    found = api.get("/events/proposed")
    if not found:
        return
    st.subheader("Proposed events", anchor=False)
    table(
        [
            {
                "event": e["event_id"],
                "type": e["event_type"],
                "use case": e["usecase_id"],
                "run": e["run_id"],
                "routed to": e.get("routed_to") or "",
            }
            for e in found
        ]
    )
    with st.container(border=True):
        labels = {f"{e['event_id']} ({e['run_id']})": e for e in found}
        pick = labels[st.selectbox("Event", list(labels), key="event_pick")]
        ident = f"{pick['run_id']}/{pick['event_id']}"
        decision = st.radio(
            "Decision", ["confirm", "dismiss"], key=f"event_decision:{ident}", horizontal=True
        )
        comment = st.text_area("Comment", key=f"event_comment:{ident}")
        if st.button("Record decision", key=f"event_submit:{ident}", type="primary"):
            api.post(
                f"/events/proposed/{ident}",
                {"confirm": decision == "confirm", "comment": comment},
            )
            st.success(
                f"{pick['event_id']} {'confirmed' if decision == 'confirm' else 'dismissed'}"
            )
