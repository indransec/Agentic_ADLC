"""Complete an escalated run (SA 8.1; FR-016): the person supplies the artifacts, then the run
goes to normal sign-off."""

from typing import Any

import streamlit as st

from adlc.ui.client import ApiClient
from adlc.ui.render import empty, page_header, table
from adlc.ui.views.run import CRUMBS, MAX_EDIT_ROWS, act, header, load, sections


def render(api: ApiClient) -> None:
    run_id = st.session_state.get("run_id")
    if not run_id:
        page_header("Escalation", crumbs=CRUMBS)
        empty("Open an escalation from your inbox.")
        return
    data, seen = load(api, run_id)
    page_header(
        "Escalation",
        "The agents could not finish this run. Supply the artifacts; the run then goes to "
        "normal sign-off.",
        crumbs=CRUMBS,
    )
    header(data)
    if not data["form"]["can_complete_escalation"]:
        st.info("You cannot complete this run.", icon=":material/lock:")
        sections(api, data)
        return
    st.subheader("Artifacts to complete", anchor=False)
    completed: dict[str, Any] = {}
    for artifact in data["artifacts"]:
        aid = artifact["id"]
        rows = artifact["rows"] if isinstance(artifact["rows"], list) else []
        with st.container(border=True):
            st.markdown(f"**{aid}**")  # the spec's artifact id
            if len(rows) > MAX_EDIT_ROWS:
                table(rows, labels=False)
                continue
            columns = artifact["columns"] or sorted({k for r in rows for k in r})
            start = [{c: r.get(c) for c in columns} for r in rows] or [{c: None for c in columns}]
            completed[aid] = st.data_editor(
                start,
                num_rows="dynamic",
                width="stretch",
                hide_index=True,
                key=f"complete:{run_id}:{aid}",
            )
    if st.button(
        "Complete escalation",
        key=f"complete:{run_id}",
        type="primary",
        icon=":material/task_alt:",
    ):
        body = {"artifacts": completed, "expected_version": seen}
        act(lambda: api.post(f"/runs/{run_id}/escalation", body), "Escalation completed")
    sections(api, data)
