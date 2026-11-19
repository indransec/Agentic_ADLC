"""ADLC web application (feature 007): sign-in, navigation, sign-out.

Run with ``streamlit run src/adlc/ui/app.py``. Every page talks to the platform API only.
"""

from collections.abc import Callable
from pathlib import Path

import streamlit as st

from adlc.config.settings import UiSettings
from adlc.ui.client import ApiClient, ApiError
from adlc.ui.render import GOTO, Colour, error
from adlc.ui.views import (
    activity,
    clarification,
    dead_letters,
    escalation,
    inbox,
    intake,
    journey,
    portfolio,
    run,
    usecases,
    waiver,
)

PRODUCT = "ADLC"
TAGLINE = "Agentic delivery lifecycle"
ASSETS = Path(__file__).resolve().parent / "assets"
LOGO = str(ASSETS / "logo.svg")
MARK = str(ASSETS / "mark.svg")
ENVIRONMENTS: dict[str, tuple[str, Colour]] = {
    "dev": ("Development", "blue"),
    "demo": ("Demo", "orange"),
}

Render = Callable[[ApiClient], None]
Entry = tuple[str, str, Render]  # title, icon, page
# The sidebar, by section
SECTIONS: dict[str, tuple[Entry, ...]] = {
    "Work": (
        ("Inbox", ":material/inbox:", inbox.render),
        ("New use case", ":material/add_circle:", intake.render),
    ),
    "Delivery": (
        ("Use cases", ":material/folder_open:", usecases.render),
        ("Journey", ":material/timeline:", journey.render),  # 013
        ("Activity", ":material/history:", activity.render),  # 013
    ),
    "Insights": (("Portfolio", ":material/insights:", portfolio.render),),  # 013
    "Operations": (("Dead letters", ":material/report:", dead_letters.render),),
}
# Pages opened from another page (an inbox item, a use case), not from the sidebar
DETAIL: tuple[Entry, ...] = (
    ("Run", ":material/play_circle:", run.render),
    ("Clarification", ":material/help:", clarification.render),
    ("Escalation", ":material/priority_high:", escalation.render),
    ("Waiver", ":material/gpp_maybe:", waiver.render),
)
HOME = "Inbox"


def client() -> ApiClient:
    if "client" not in st.session_state:  # tests inject a client before the first run
        st.session_state["client"] = ApiClient.for_url(UiSettings().api_url)
    api: ApiClient = st.session_state["client"]
    return api


def slug(title: str) -> str:
    return title.lower().replace(" ", "-")


def runner(render: Render) -> Callable[[], None]:
    """A page body: the session's own client, and the API's refusals shown as such."""

    def page() -> None:
        api = client()
        try:
            render(api)
        except ApiError as exc:
            if exc.signed_out:  # the session expired: sign in again, keep nothing else
                sign_out(api)
                st.rerun()
            error(exc)

    return page


def build_pages() -> dict[str, st.Page]:
    entries = [e for section in SECTIONS.values() for e in section] + list(DETAIL)
    return {
        title: st.Page(
            runner(render), title=title, icon=icon, url_path=slug(title), default=title == HOME
        )
        for title, icon, render in entries
    }


def environment_badge() -> None:
    env = UiSettings().env
    if env in ENVIRONMENTS:
        name, colour = ENVIRONMENTS[env]
        st.badge(f"{name} environment", color=colour, icon=":material/dns:")


def sign_in(api: ApiClient) -> None:
    _, middle, _ = st.columns([1, 1.2, 1])
    with middle:
        st.space("large")
        st.image(LOGO, width=168)
        st.subheader("Sign in", anchor=False)
        st.caption(f"{TAGLINE}: agents build, people decide.")
        environment_badge()
        with st.form("sign_in"):
            account = st.text_input("Account", key="account", placeholder="your account name")
            password = st.text_input("Password", type="password", key="password")
            submitted = st.form_submit_button("Sign in", type="primary", width="stretch")
        if submitted:
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


def sidebar(api: ApiClient, built: dict[str, st.Page]) -> None:
    person = api.person or {}
    with st.sidebar:
        environment_badge()
        for section, entries in SECTIONS.items():
            st.caption(section)
            for title, _, _ in entries:
                st.page_link(built[title])
        st.divider()
        with st.container(border=True):
            st.text(str(person.get("display_name", "")))  # from the accounts file: plain text
            st.caption(", ".join(str(r).replace("_", " ") for r in person.get("roles", [])))
            if st.button("Sign out", key="sign_out", icon=":material/logout:", width="stretch"):
                sign_out(api)
                st.rerun()


def main() -> None:
    st.set_page_config(page_title=PRODUCT, page_icon=MARK, layout="wide")
    st.logo(LOGO, icon_image=MARK, size="large")
    api = client()
    if api.token is None:
        sign_in(api)
        return
    built = build_pages()
    current = st.navigation(list(built.values()), position="hidden")
    if (goto := st.session_state.pop(GOTO, None)) in built and goto != current.title:
        st.switch_page(built[goto])  # a page asked for by name (render.navigate)
    st.session_state["page"] = current.title
    sidebar(api, built)
    current.run()


main()
