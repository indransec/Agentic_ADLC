"""Dead-lettered events and re-queue (SA 8.1; FR-018). The API allows the CoE role only."""

import streamlit as st

from adlc.ui.client import ApiClient, ApiError
from adlc.ui.render import page_header, table
from adlc.ui.views.run import act


def render(api: ApiClient) -> None:
    page_header(
        "Dead letters",
        "Events the platform could not deliver after its retries. Inspect them, then re-queue.",
    )
    try:
        found = api.get("/dead-letters")
    except ApiError as exc:
        if exc.kind != "not_allowed":
            raise
        st.info("Dead letters are handled by the CoE role.", icon=":material/lock:")
        return
    table(found, empty_text="No dead letters: every event was delivered.")
    ids = [str(d["event_id"]) for d in found]
    if not ids:
        return
    with st.container(border=True):
        pick = st.selectbox("Event", ids, key="dead_pick")
        detail_column, requeue_column, _ = st.columns([2, 2, 3])
        show = detail_column.button(
            "Show payload and history",
            key="dead_detail",
            icon=":material/visibility:",
            width="stretch",
        )  # 013 US5
        requeue = requeue_column.button(
            "Re-queue",
            key="dead_requeue",
            icon=":material/replay:",
            type="primary",
            width="stretch",
        )
        if show:
            detail = api.get(f"/dead-letters/{pick}")
            st.caption("Payload")
            st.json(detail.get("payload") or {})
            st.caption("Re-queue history")
            table(detail.get("history") or [], key="dead_history", empty_text="Never re-queued.")
        if requeue:
            act(lambda: api.post(f"/dead-letters/{pick}/requeue"), "Re-queued")
