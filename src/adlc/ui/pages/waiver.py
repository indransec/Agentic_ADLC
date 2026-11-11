"""Approve or reject a waiver (SA 8.1; FR-017)."""

import streamlit as st

from adlc.ui.client import ApiClient
from adlc.ui.pages.run import act, header, load
from adlc.ui.render import field


def render(api: ApiClient) -> None:
    st.header("Waiver")
    waiver_id = st.session_state.get("waiver_id")
    run_id = st.session_state.get("run_id")
    if not waiver_id or not run_id:
        st.caption("Open a waiver from the inbox.")
        return
    data, _ = load(api, run_id)
    header(data)
    waiver = data["waiver"]
    if waiver is None or waiver["waiver_id"] != waiver_id:
        st.caption("This waiver is no longer pending.")
        return
    for name in (
        "waiver_id",
        "status",
        "proposed_by",
        "waiver_owner",
        "compensating_control",
        "expiry",
    ):
        field(name.replace("_", " ").capitalize(), waiver.get(name))
    # The other values the spec requires for an exception (for example a risk acceptance or
    # conditions), as the proposer typed them.
    for name, value in sorted((waiver.get("requires") or {}).items()):
        if waiver.get(name) is None and name not in ("waiver_id", "status", "proposed_by"):
            field(str(name).replace("_", " ").capitalize(), value)
    choice = st.radio("Decision", ["approve", "reject"], key=f"waiver:{waiver_id}", horizontal=True)
    comment = st.text_area("Comment", key=f"waiver_comment:{waiver_id}")
    if st.button("Record waiver decision", key=f"waiver_send:{waiver_id}"):
        body = {"approve": choice == "approve", "comment": comment or None}
        act(lambda: api.post(f"/waivers/{waiver_id}/decision", body), "Waiver decision recorded")
