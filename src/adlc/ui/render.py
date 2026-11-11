"""Safe display helpers (007 FR-013, research R-07).

Text written by agents or people is shown only through ``st.text``, ``st.code``, ``st.dataframe``
and ``st.data_editor``, which never interpret Markdown or HTML. Markdown is used only for labels
the platform writes itself (``label`` arguments below are always platform text).
"""

from collections.abc import Mapping, Sequence
from typing import Any

import streamlit as st

from adlc.ui.client import ApiError


def field(label: str, value: Any) -> None:
    """A labelled value; the value is plain text whatever it contains."""
    st.caption(label)
    st.text("" if value is None else str(value))


def table(rows: Sequence[Mapping[str, Any]], key: str | None = None) -> None:
    if rows:
        st.dataframe([dict(r) for r in rows], use_container_width=True, hide_index=True, key=key)
    else:
        st.caption("(none)")


def error(exc: ApiError) -> None:
    """The API's reason, as plain text (never a stack trace)."""
    st.error(f"{exc.kind.replace('_', ' ')} ({exc.status})")
    st.text(exc.detail)
