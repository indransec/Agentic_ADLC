"""Activity feed (feature 013, US2; SA §12.2): agent, reviewer, human and orchestrator actions,
newest first, filterable; refreshes itself and keeps the filters."""

import streamlit as st

from adlc.ui.client import ApiClient
from adlc.ui.pages.journey import refresh_seconds
from adlc.ui.render import table

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


def render(api: ApiClient) -> None:
    st.header("Activity")
    usecases = [""] + [u["usecase_id"] for u in api.get("/usecases")]
    columns = st.columns(4)
    columns[0].selectbox("Use case", usecases, key="activity_usecase")
    columns[1].text_input("Terminal", key="activity_terminal")
    columns[2].selectbox("Actor", ACTORS, key="activity_actor")
    columns[3].selectbox("Step", STEPS, key="activity_step")
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
        st.caption("No activity matches.")
        return
    table(found, key="activity_feed")
