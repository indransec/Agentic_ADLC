"""Approve or reject a waiver (SA 8.1; FR-017)."""

import streamlit as st

from adlc.ui.client import ApiClient
from adlc.ui.render import empty, field, page_header
from adlc.ui.views.run import CRUMBS, act, header, load

SHOWN = ("waiver_id", "status", "proposed_by", "waiver_owner", "compensating_control", "expiry")


def render(api: ApiClient) -> None:
    waiver_id = st.session_state.get("waiver_id")
    run_id = st.session_state.get("run_id")
    if not waiver_id or not run_id:
        page_header("Waiver", crumbs=CRUMBS)
        empty("Open a waiver from your inbox.")
        return
    data, _ = load(api, run_id)
    page_header(
        "Waiver",
        "An exception was proposed for a failed control. Approve it or reject it.",
        crumbs=CRUMBS,
    )
    header(data)
    waiver = data["waiver"]
    if waiver is None or waiver["waiver_id"] != waiver_id:
        empty("This waiver is no longer pending.")
        return
    with st.container(border=True):
        columns = st.columns(3)
        for n, name in enumerate(SHOWN):
            with columns[n % 3]:
                field(name.replace("_", " ").capitalize(), waiver.get(name))
        # The other values the spec requires for an exception (for example a risk acceptance or
        # conditions), as the proposer typed them.
        for name, value in sorted((waiver.get("requires") or {}).items()):
            if waiver.get(name) is None and name not in ("waiver_id", "status", "proposed_by"):
                field(str(name).replace("_", " ").capitalize(), value)
    with st.container(border=True):
        choice = st.radio(
            "Decision", ["approve", "reject"], key=f"waiver:{waiver_id}", horizontal=True
        )
        comment = st.text_area("Comment", key=f"waiver_comment:{waiver_id}")
        if st.button(
            "Record waiver decision",
            key=f"waiver_send:{waiver_id}",
            type="primary",
            icon=":material/gavel:",
        ):
            body = {"approve": choice == "approve", "comment": comment or None}
            act(
                lambda: api.post(f"/waivers/{waiver_id}/decision", body), "Waiver decision recorded"
            )
