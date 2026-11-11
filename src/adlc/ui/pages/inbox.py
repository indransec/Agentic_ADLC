"""Inbox page: filled in by US2."""

import streamlit as st

from adlc.ui.client import ApiClient


def render(api: ApiClient) -> None:
    st.header("Inbox")
