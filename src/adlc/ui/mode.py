"""Inbox or console (feature 019, research R-01).

The web app is the operations console when the board sync is enabled and the inbox when it is
not. It asks the platform API (``GET /board/mode``) at sign-in and again at most every
``REREAD_SECONDS``; on an error it keeps the last answer, or the inbox when it has none, and says
so. The answer also gives the board's address for browsers and whether the person operates the
sync.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

import streamlit as st

from adlc.ui.client import ApiClient, ApiError

KEY = "board_mode"
REREAD_SECONDS = 60.0
INBOX: dict[str, Any] = {"mode": "inbox", "board_url": None, "can_operate": False}


def now() -> float:
    """The clock the re-read uses (tests replace it)."""
    return time.monotonic()


def current(api: ApiClient) -> dict[str, Any]:
    """The mode answer, read again when older than ``REREAD_SECONDS``."""
    kept: dict[str, Any] | None = st.session_state.get(KEY)
    if kept is not None and now() - kept["at"] < REREAD_SECONDS:
        return dict(kept["answer"])
    try:
        answer = dict(api.get("/board/mode"))
        stale = False
    except ApiError as exc:
        if exc.signed_out:
            raise
        answer = dict(kept["answer"]) if kept is not None else dict(INBOX)
        stale = True
    st.session_state[KEY] = {"answer": answer, "at": now(), "stale": stale}
    return answer


def stale() -> bool:
    """The last read failed: the mode shown is the last known one (or the inbox)."""
    kept = st.session_state.get(KEY)
    return bool(kept and kept.get("stale"))


def is_console(api: ApiClient) -> bool:
    return current(api).get("mode") == "console"


def board_url(api: ApiClient) -> str | None:
    value = current(api).get("board_url")
    return str(value) if value else None


def can_operate(api: ApiClient) -> bool:
    return bool(current(api).get("can_operate"))


def item_url(api: ApiClient, kind: str, object_id: str) -> str | None:
    """The address of the board item showing ``object_id``, or None when it is not there yet."""
    try:
        found = api.get(f"/board/items/{kind}/{quote(object_id, safe='/')}")
    except ApiError as exc:
        if exc.signed_out:
            raise
        return None
    url = str(found.get("url") or "")
    return url if url.startswith(("http://", "https://")) else None
