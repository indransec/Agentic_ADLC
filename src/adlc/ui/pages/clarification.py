"""Answer a clarification (SA 8.1; FR-015). Questions are agent text, shown as plain text."""

from typing import Any

import streamlit as st

from adlc.ui.client import ApiClient
from adlc.ui.pages.run import act, header, load
from adlc.ui.render import field


def render(api: ApiClient) -> None:
    st.header("Clarification")
    clarification_id = st.session_state.get("clarification_id")
    run_id = st.session_state.get("run_id")
    if not clarification_id or not run_id:
        st.caption("Open a clarification from the inbox.")
        return
    data, _ = load(api, run_id)
    header(data)
    found: dict[str, Any] | None = next(
        (c for c in data["clarifications"] if c["clarification_id"] == clarification_id), None
    )
    if found is None:
        st.caption("This clarification is not on the run.")
        return
    field("Asked by", found["asked_by"])
    field("Addressed to", found["addressed_role"])
    field("Already looked in", ", ".join(str(x) for x in found.get("looked_in") or []))
    if found["answered_by"] is not None:
        field("Answered by", found["answered_by"])
        for answer in found["answers"] or []:
            st.text(str(answer))
        return
    answers = []
    for n, question in enumerate(found["questions"]):
        st.caption(f"Question {n + 1}")
        st.text(str(question))
        answers.append(st.text_area("Answer", key=f"answer:{clarification_id}:{n}"))
    if st.button("Send answers", key=f"send:{clarification_id}"):
        path = f"/clarifications/{clarification_id}/answers"
        act(lambda: api.post(path, {"answers": answers}), "Answers sent")
