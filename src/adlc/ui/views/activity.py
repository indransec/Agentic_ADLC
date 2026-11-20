"""Activity feed (feature 013, US2; SA §12.2): agent, reviewer, human and orchestrator actions,
newest first, filterable; refreshes itself and keeps the filters."""

import streamlit as st

from adlc.ui.client import ApiClient
from adlc.ui.render import empty, page_header, table
from adlc.ui.views.journey import refresh_seconds

ACTORS = ("", "agent", "reviewer", "human", "orchestrator", "system")
STEPS = (
    "",
    "prerequisites",
    "build",
    "controls",
    "review",
    "clarification",
    "sign_off",
    "waiver",
    "escalation",
    "close",
    "route",
    "timer",
)


def any_or(value: str) -> str:
    return value.replace("_", " ").capitalize() if value else "Any"


def render(api: ApiClient) -> None:
    page_header(
        "Activity", "What agents, reviewers, people and the orchestrator did, newest first."
    )
    usecases = [""] + [u["usecase_id"] for u in api.get("/usecases")]
    with st.container(border=True):
        columns = st.columns(4)
        columns[0].selectbox(
            "Use case", usecases, key="activity_usecase", format_func=lambda v: v or "Any"
        )
        columns[1].text_input("Terminal", key="activity_terminal", placeholder="Any terminal")
        columns[2].selectbox("Actor", ACTORS, key="activity_actor", format_func=any_or)
        columns[3].selectbox("Step", STEPS, key="activity_step", format_func=any_or)
    feed(api)


@st.fragment(run_every=refresh_seconds())
def feed(api: ApiClient) -> None:
    params = {
        "usecase_id": st.session_state.get("activity_usecase") or None,
        "terminal_id": (st.session_state.get("activity_terminal") or "").strip() or None,
        "actor_type": st.session_state.get("activity_actor") or None,
        "step": st.session_state.get("activity_step") or None,
    }
    found = api.get("/dashboard/activity", **{k: v for k, v in params.items() if v})
    if not found:
        empty("No activity matches these filters.")
        return
    st.caption(f"{len(found)} action(s)")
    table(found, key="activity_feed")
