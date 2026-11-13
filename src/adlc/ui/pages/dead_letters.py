"""Dead-lettered events and re-queue (SA 8.1; FR-018). The API allows the CoE role only."""

import streamlit as st

from adlc.ui.client import ApiClient, ApiError
from adlc.ui.pages.run import act
from adlc.ui.render import table


def render(api: ApiClient) -> None:
    st.header("Dead letters")
    try:
        found = api.get("/dead-letters")
    except ApiError as exc:
        if exc.kind != "not_allowed":
            raise
        st.caption("Dead letters are handled by the CoE role.")
        return
    table(found)
    ids = [str(d["event_id"]) for d in found]
    if not ids:
        return
    pick = st.selectbox("Event", ids, key="dead_pick")
    if st.button("Show payload and history", key="dead_detail"):  # 013 US5
        detail = api.get(f"/dead-letters/{pick}")
        st.json(detail.get("payload") or {})
        table(detail.get("history") or [], key="dead_history")
    if st.button("Re-queue", key="dead_requeue"):
        act(lambda: api.post(f"/dead-letters/{pick}/requeue"), "Re-queued")
