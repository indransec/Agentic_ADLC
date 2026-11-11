"""ADLC web application (feature 007): sign-in, navigation, sign-out.

Run with ``streamlit run src/adlc/ui/app.py``. Every page talks to the platform API only.
"""

import streamlit as st

from adlc.config.settings import UiSettings
from adlc.ui.client import ApiClient, ApiError
from adlc.ui.pages import (
    clarification,
    dead_letters,
    escalation,
    inbox,
    intake,
    run,
    usecases,
    waiver,
)
from adlc.ui.render import error

PAGES = {
    "Inbox": inbox.render,
    "New use case": intake.render,
    "Use cases": usecases.render,
    "Run": run.render,
    "Clarification": clarification.render,
    "Escalation": escalation.render,
    "Waiver": waiver.render,
    "Dead letters": dead_letters.render,
}


def client() -> ApiClient:
    if "client" not in st.session_state:  # tests inject a client before the first run
        st.session_state["client"] = ApiClient.for_url(UiSettings().api_url)
    api: ApiClient = st.session_state["client"]
    return api


def sign_in(api: ApiClient) -> None:
    st.title("ADLC")
    with st.form("sign_in"):
        account = st.text_input("Account", key="account")
        password = st.text_input("Password", type="password", key="password")
        if st.form_submit_button("Sign in"):
            try:
                api.sign_in(account, password)
            except ApiError as exc:
                error(exc)
            else:
                st.rerun()


def sign_out(api: ApiClient) -> None:
    api.sign_out()
    for key in list(st.session_state):
        if key != "client":
            del st.session_state[key]


def main() -> None:
    st.set_page_config(page_title="ADLC", layout="wide")
    api = client()
    if api.token is None:
        sign_in(api)
        return
    person = api.person or {}
    if goto := st.session_state.pop("goto", None):
        st.session_state["page"] = goto
        st.session_state.pop("run_input", None)  # show the run just chosen
    with st.sidebar:
        st.text(f"{person.get('display_name', '')} ({', '.join(person.get('roles', []))})")
        page = st.radio("Page", list(PAGES), key="page")
        if st.button("Sign out", key="sign_out"):
            sign_out(api)
            st.rerun()
    try:
        PAGES[page](api)
    except ApiError as exc:
        if exc.signed_out:  # the session expired: sign in again, keep nothing else
            sign_out(api)
            st.rerun()
        error(exc)


main()
