"""Pages whose action is now made on the board (feature 019, US3; research R-05).

In console mode the inbox, the intake form and the clarification, escalation and waiver pages are
still registered (old addresses resolve) but say where the action is made now, with a link.
"""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from adlc.ui import mode
from adlc.ui.client import ApiClient
from adlc.ui.render import empty, page_header

ACTIONS = {
    "Inbox": "Sign-offs, decisions, clarifications, waivers and escalations",
    "New use case": "A new use case (create an Epic in the use cases area)",
    "Clarification": "Answering a clarification (its item under the run)",
    "Escalation": "Completing an escalation (the run's decision field)",
    "Waiver": "Deciding a waiver (the run's decision field)",
}


def renderer(title: str) -> Callable[[ApiClient], None]:
    def render(api: ApiClient) -> None:
        page_header(title)
        action = ACTIONS.get(title, title)
        st.info(f"{action}: made on the board now.", icon=":material/view_kanban:")
        url = mode.board_url(api)
        if url:
            st.link_button("Open the board", url, icon=":material/open_in_new:")
        else:
            empty("The board's address is not known.")

    return render
