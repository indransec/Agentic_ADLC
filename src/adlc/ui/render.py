"""Safe display helpers (007 FR-013, research R-07).

Text written by agents or people is shown only through ``st.text``, ``st.code``, ``st.dataframe``
and ``st.data_editor``, which never interpret Markdown or HTML. Markdown is used only for labels
the platform writes itself (``label`` arguments below are always platform text).
"""

import json
from collections.abc import Mapping, Sequence
from typing import Any

import streamlit as st

from adlc.ui.client import ApiError


def field(label: str, value: Any) -> None:
    """A labelled value; the value is plain text whatever it contains."""
    st.caption(label)
    st.text("" if value is None else str(value))


def cell(value: Any) -> Any:
    """Nested values are shown as JSON text, so every cell is a scalar."""
    if isinstance(value, Mapping | list | tuple):
        return json.dumps(value, default=str, ensure_ascii=False)
    return value


def table(rows: Sequence[Mapping[str, Any]], key: str | None = None) -> None:
    if rows:
        st.dataframe(
            [{k: cell(v) for k, v in r.items()} for r in rows],
            use_container_width=True,
            hide_index=True,
            key=key,
        )
    else:
        st.caption("(none)")


def navigate(page: str, *, run_id: str | None = None, **state: Any) -> None:
    """Go to another page on the next run (the page selector cannot change once drawn)."""
    if run_id is not None:
        st.session_state["run_id"] = run_id
    st.session_state.update(state)
    st.session_state["goto"] = page
    st.rerun(scope="app")


def error(exc: ApiError) -> None:
    """The API's reason, as plain text (never a stack trace)."""
    st.error(f"{exc.kind.replace('_', ' ')} ({exc.status})")
    st.text(exc.detail)
