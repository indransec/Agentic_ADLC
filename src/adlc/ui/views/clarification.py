"""Answer a clarification (SA 8.1; FR-015). Questions are agent text, shown as plain text."""

from typing import Any

import streamlit as st

from adlc.ui.client import ApiClient
from adlc.ui.render import empty, field, page_header
from adlc.ui.views.run import CRUMBS, act, header, load


def render(api: ApiClient) -> None:
    clarification_id = st.session_state.get("clarification_id")
    run_id = st.session_state.get("run_id")
    if not clarification_id or not run_id:
        page_header("Clarification", crumbs=CRUMBS)
        empty("Open a clarification from your inbox.")
        return
    data, _ = load(api, run_id)
    page_header(
        "Clarification",
        "An agent needs facts it could not find. Your answers go back to the run.",
        crumbs=CRUMBS,
    )
    header(data)
    found: dict[str, Any] | None = next(
        (c for c in data["clarifications"] if c["clarification_id"] == clarification_id), None
    )
    if found is None:
        empty("This clarification is not on the run.")
        return
    with st.container(border=True):
        asked, addressed, looked = st.columns(3)
        with asked:
            field("Asked by", found["asked_by"])
        with addressed:
            field("Addressed to", found["addressed_role"])
        with looked:
            field("Already looked in", ", ".join(str(x) for x in found.get("looked_in") or []))
    answered = found["answered_by"] is not None
    given = list(found["answers"] or []) if answered else []
    answers = []
    for n, question in enumerate(found["questions"]):
        with st.container(border=True):
            st.caption(f"Question {n + 1}")
            st.text(str(question))
            if answered:
                st.caption("Answer")
                st.text(str(given[n]) if n < len(given) else "")
            else:
                answers.append(st.text_area("Answer", key=f"answer:{clarification_id}:{n}"))
    if answered:
        field("Answered by", found["answered_by"])
        return
    if st.button(
        "Send answers", key=f"send:{clarification_id}", type="primary", icon=":material/send:"
    ):
        path = f"/clarifications/{clarification_id}/answers"
        act(lambda: api.post(path, {"answers": answers}), "Answers sent")
