"""Safe display helpers and the shared page components (007 FR-013, research R-07).

Text written by agents or people is shown only through ``st.text``, ``st.code``, ``st.dataframe``
and ``st.data_editor``, which never interpret Markdown or HTML. Markdown is used only for labels
the platform writes itself (``label`` and ``title`` arguments below are always platform text), and
a status badge shows only the platform's own words for a known value (anything else is plain text).
"""

import json
from collections.abc import Mapping, Sequence
from typing import Any, Literal

import streamlit as st

from adlc.ui import format as fmt
from adlc.ui.client import ApiError

GOTO = "goto"  # the title of the page to open on the next run (app.py switches to it)
TIME_FORMAT = "D MMM YYYY, HH:mm"

Colour = Literal["blue", "green", "orange", "red", "violet", "gray"]

# A known value -> (what people read, badge colour, icon). The platform's own state machine,
# outcome and status words; nothing terminal- or use-case-specific.
STATUS: dict[str, tuple[str, Colour, str]] = {
    # run states
    "opened": ("Opened", "blue", ":material/radio_button_checked:"),
    "blocked": ("Blocked", "red", ":material/block:"),
    "building": ("Building", "blue", ":material/construction:"),
    "awaiting_clarification": ("Awaiting clarification", "orange", ":material/help:"),
    "checking": ("Checking", "blue", ":material/fact_check:"),
    "reviewing": ("Reviewing", "blue", ":material/rate_review:"),
    "awaiting_sign_off": ("Awaiting sign-off", "orange", ":material/approval:"),
    "escalated": ("Escalated", "red", ":material/priority_high:"),
    "closed": ("Closed", "gray", ":material/check_circle:"),
    # outcomes
    "pass": ("Passed", "green", ":material/check_circle:"),
    "rework": ("Rework", "orange", ":material/replay:"),
    "exception": ("Exception", "violet", ":material/gpp_maybe:"),
    "terminate": ("Terminated", "red", ":material/cancel:"),
    # use case status
    "active": ("Active", "blue", ":material/play_circle:"),
    "terminated": ("Terminated", "red", ":material/cancel:"),
    # risk tiers
    "low": ("Low risk", "green", ":material/shield:"),
    "medium": ("Medium risk", "orange", ":material/shield:"),
    "high": ("High risk", "red", ":material/shield:"),
}
# The same colours as hex, for charts (.streamlit/config.toml defines the badge colours)
STATUS_COLOURS: dict[Colour, str] = {
    "blue": "#2F5DAA",
    "green": "#2E7D4F",
    "orange": "#B8621B",
    "red": "#B83B3B",
    "violet": "#6E4BB8",
    "gray": "#9AA3B2",
}


def field(label: str, value: Any) -> None:
    """A labelled value; the value is plain text whatever it contains."""
    st.caption(label)
    st.text(fmt.MISSING if value is None or value == "" else str(value))


def page_header(title: str, caption: str | None = None, *, crumbs: Sequence[str] = ()) -> None:
    """The page title, where it sits (platform page names only) and what the page is for."""
    if crumbs:
        st.caption("  ›  ".join([*crumbs, title]))
    st.header(title, anchor=False)
    if caption:
        st.caption(caption)


def status_badge(value: Any, *, text: str | None = None) -> None:
    """A coloured badge for a known platform value; anything else as plain text.

    ``text`` (platform words) replaces the badge's wording; it is used only for a known value.
    """
    known = STATUS.get(str(value)) if value is not None else None
    if known is None:
        st.text(fmt.MISSING if value in (None, "") else str(value))
        return
    word, colour, icon = known
    st.badge(text or word, color=colour, icon=icon)


def status_colour(value: Any) -> str:
    known = STATUS.get(str(value))
    return STATUS_COLOURS[known[1] if known else "gray"]


def status_text(value: Any) -> str:
    """The plain word for a known value (for table cells); unknown values unchanged."""
    known = STATUS.get(str(value)) if value is not None else None
    return known[0] if known else ("" if value is None else str(value))


def empty(message: str) -> None:
    """An empty section or page, said once and quietly."""
    st.caption(f":material/inbox: {message}")


def cell(value: Any) -> Any:
    """Nested values are shown as JSON text, so every cell is a scalar."""
    if isinstance(value, Mapping | list | tuple):
        return json.dumps(value, default=str, ensure_ascii=False)
    return value


def _is_cost(key: str) -> bool:
    return "cost" in key.lower()


def table(
    rows: Sequence[Mapping[str, Any]],
    key: str | None = None,
    *,
    labels: bool = True,
    columns: Mapping[str, Any] | None = None,
    empty_text: str = "None.",
) -> None:
    """A read-only table: times as dates, costs in dollars, readable column names.

    ``labels=False`` keeps the column names as they are (artifact columns are the spec's names).
    The underlying column names never change, so a table reads the same through the API.
    """
    if not rows:
        empty(empty_text)
        return
    data = [{k: cell(v) for k, v in r.items()} for r in rows]
    names = list(dict.fromkeys(k for r in data for k in r))
    config: dict[str, Any] = {}
    for name in names:
        values = [r.get(name) for r in data if r.get(name) not in (None, "")]
        heading = fmt.label(name) if labels else name
        if values and all(fmt.parse_time(v) is not None for v in values):
            for r in data:
                r[name] = fmt.parse_time(r.get(name))
            config[name] = st.column_config.DatetimeColumn(heading, format=TIME_FORMAT)
        elif values and _is_cost(name) and all(isinstance(v, int | float) for v in values):
            config[name] = st.column_config.NumberColumn(heading, format="$%.4f")
        elif heading != name:
            config[name] = st.column_config.Column(heading)
    config.update(columns or {})
    st.dataframe(data, width="stretch", hide_index=True, key=key, column_config=config)


def open_picker(
    options: Sequence[str], *, select_key: str, button_key: str, label: str = "Open"
) -> str | None:
    """Choose one item and open it: the choice and its button on one line.

    Returns the chosen option when the button is pressed. Options are platform-built labels.
    """
    if not options:
        return None
    choice, action = st.columns([5, 1], vertical_alignment="bottom")
    pick = choice.selectbox(label, list(options), key=select_key)
    pressed = action.button(
        "Open", key=button_key, icon=":material/open_in_new:", type="primary", width="stretch"
    )
    return pick if pressed else None


def navigate(page: str, *, run_id: str | None = None, **state: Any) -> None:
    """Open another page by its title, carrying the item to show in the session state."""
    if run_id is not None:
        st.session_state["run_id"] = run_id
    st.session_state.update(state)
    st.session_state[GOTO] = page
    st.rerun(scope="app")


def error(exc: ApiError) -> None:
    """The API's reason, as plain text (never a stack trace)."""
    st.error(
        f"The platform refused this: {exc.kind.replace('_', ' ')} (HTTP {exc.status})",
        icon=":material/error:",
    )
    st.text(exc.detail)
