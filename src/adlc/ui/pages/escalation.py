"""Complete an escalated run (SA 8.1; FR-016): the person supplies the artifacts, then the run
goes to normal sign-off."""

from typing import Any

import streamlit as st

from adlc.ui.client import ApiClient
from adlc.ui.pages.run import MAX_EDIT_ROWS, act, header, load, sections
from adlc.ui.render import table


def render(api: ApiClient) -> None:
    st.header("Escalation")
    run_id = st.session_state.get("run_id")
    if not run_id:
        st.caption("Open an escalation from the inbox.")
        return
    data, seen = load(api, run_id)
    header(data)
    run = data["run"]
    st.text(f"Escalated: {run['state']}")
    if not data["form"]["can_complete_escalation"]:
        st.caption("You cannot complete this run.")
        sections(data)
        return
    st.subheader("Artifacts to complete")
    completed: dict[str, Any] = {}
    for artifact in data["artifacts"]:
        aid = artifact["id"]
        rows = artifact["rows"] if isinstance(artifact["rows"], list) else []
        st.caption(aid)
        if len(rows) > MAX_EDIT_ROWS:
            table(rows)
            continue
        columns = artifact["columns"] or sorted({k for r in rows for k in r})
        start = [{c: r.get(c) for c in columns} for r in rows] or [{c: None for c in columns}]
        completed[aid] = st.data_editor(
            start,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key=f"complete:{run_id}:{aid}",
        )
    sections(data)
    if st.button("Complete escalation", key=f"complete:{run_id}"):
        body = {"artifacts": completed, "expected_version": seen}
        act(lambda: api.post(f"/runs/{run_id}/escalation", body), "Escalation completed")
