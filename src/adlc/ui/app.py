"""ADLC web application (feature 007): sign-in, navigation, sign-out.

Run with ``streamlit run src/adlc/ui/app.py``. Every page talks to the platform API only.

019: when the board sync is enabled (the API says so, ``adlc.ui.mode``) the app is the operations
console: the pages whose action is made on the board say so, the sidebar lists the console's pages
and the default page is Use cases. Every page stays registered, so old addresses resolve. The
board's evidence link (``?run=``) opens the Run page, after sign-in if needed.
"""

from collections.abc import Callable
from pathlib import Path

import streamlit as st

from adlc.config.settings import UiSettings
from adlc.ui import mode
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
    moved,
    portfolio,
    run,
    sync,
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
CONSOLE_HOME = "Use cases"  # 019
# 019: actions made on the board in console mode (the pages render a notice instead)
ON_THE_BOARD = frozenset({"Inbox", "New use case", "Clarification", "Escalation", "Waiver"})
# 019: offered in the sidebar's Operations section to the people who operate the board sync
OPERATOR: tuple[Entry, ...] = (("Sync status", ":material/sync:", sync.render),)
DEEP_LINK = "deep_link_routed"


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


def build_pages(console: bool = False) -> dict[str, st.Page]:
    entries = [e for section in SECTIONS.values() for e in section] + list(DETAIL) + list(OPERATOR)
    home = CONSOLE_HOME if console else HOME
    return {
        title: st.Page(
            runner(moved.renderer(title) if console and title in ON_THE_BOARD else render),
            title=title,
            icon=icon,
            url_path=slug(title),
            default=title == home,
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


def sidebar(api: ApiClient, built: dict[str, st.Page], console: bool = False) -> None:
    person = api.person or {}
    with st.sidebar:
        environment_badge()
        if mode.stale():
            st.caption(
                ":material/warning: The board mode could not be read; showing the last known."
            )
        for section, entries in SECTIONS.items():
            titles = [t for t, _, _ in entries if not (console and t in ON_THE_BOARD)]
            if section == "Operations" and mode.can_operate(api):
                titles += [t for t, _, _ in OPERATOR]
            if not titles:
                continue
            st.caption(section)
            for title in titles:
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
    try:
        console = mode.is_console(api)
    except ApiError:  # signed out meanwhile: sign in again, keep nothing else
        sign_out(api)
        st.rerun()
    built = build_pages(console)
    current = st.navigation(list(built.values()), position="hidden")
    if DEEP_LINK not in st.session_state:  # 019: the board's evidence link opens the run
        st.session_state[DEEP_LINK] = True
        if (linked := st.query_params.get("run")) and current.title != "Run":
            st.session_state["run_id"] = linked
            st.switch_page(built["Run"])
    if (goto := st.session_state.pop(GOTO, None)) in built and goto != current.title:
        st.switch_page(built[goto])  # a page asked for by name (render.navigate)
    st.session_state["page"] = current.title
    sidebar(api, built, console)
    current.run()


main()
