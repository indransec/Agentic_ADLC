"""New use case (SA 8.1 "Submit use case")."""

import streamlit as st

from adlc.ui.client import ApiClient, ApiError
from adlc.ui.render import error, navigate


def render(api: ApiClient) -> None:
    st.header("New use case")
    with st.form("intake", clear_on_submit=False):
        name = st.text_input("Name", max_chars=200, key="intake_name")
        text = st.text_area(
            "Describe the problem, the people involved and the outcome you want",
            max_chars=20_000,
            height=240,
            key="intake_text",
        )
        submitted = st.form_submit_button("Submit")
    if submitted:
        try:
            answer = api.post("/usecases", {"name": name, "intake_text": text})
        except ApiError as exc:
            error(exc)
            return
        navigate("Use cases", usecase_id=answer["usecase_id"], submitted=answer["usecase_id"])
