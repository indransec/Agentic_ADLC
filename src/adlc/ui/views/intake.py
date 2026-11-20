"""New use case (SA 8.1 "Submit use case")."""

import streamlit as st

from adlc.ui.client import ApiClient, ApiError
from adlc.ui.render import error, navigate, page_header


def render(api: ApiClient) -> None:
    page_header(
        "New use case",
        "Describe the problem in your own words. The first terminal turns it into a scoped use "
        "case and asks you if anything is missing.",
    )
    form, guide = st.columns([3, 1], gap="large")
    with form, st.form("intake", clear_on_submit=False):
        name = st.text_input(
            "Name", max_chars=200, key="intake_name", placeholder="A short name for the use case"
        )
        text = st.text_area(
            "Describe the problem, the people involved and the outcome you want",
            max_chars=20_000,
            height=280,
            key="intake_text",
        )
        submitted = st.form_submit_button("Submit", type="primary", icon=":material/send:")
    with guide, st.container(border=True):
        st.caption("A good description says")
        st.markdown(
            "- who has the problem today\n"
            "- what they do now, and what goes wrong\n"
            "- the data or systems involved\n"
            "- what a good outcome looks like"
        )
    if submitted:
        try:
            answer = api.post("/usecases", {"name": name, "intake_text": text})
        except ApiError as exc:
            error(exc)
            return
        navigate("Use cases", usecase_id=answer["usecase_id"], submitted=answer["usecase_id"])
