"""The web application under ``streamlit.testing.v1.AppTest``, driven through the real API (007
research R-08): its client's HTTP calls go to FastAPI's test client over the harness database."""

from typing import Any

from streamlit.testing.v1 import AppTest

from adlc.ui.client import ApiClient
from tests.support.api import PASSWORD, Api
from tests.support.pg import REPO_ROOT

APP = REPO_ROOT / "src" / "adlc" / "ui" / "app.py"


def open_ui(api: Api) -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.session_state["client"] = ApiClient(api.client)
    return at.run()


def sign_in(at: AppTest, role: str) -> AppTest:
    at.text_input(key="account").input(f"{role}-person")
    at.text_input(key="password").input(PASSWORD)
    at.button[0].click()
    return at.run()


def go(at: AppTest, page: str) -> AppTest:
    at.radio(key="page").set_value(page)
    return at.run()


def texts(at: AppTest) -> list[str]:
    return [t.value for t in at.text]


def frame(at: AppTest, column: str) -> Any:
    """The first table on the page that has ``column``."""
    for element in at.dataframe:
        if column in element.value.columns:
            return element.value
    raise AssertionError(f"no table with column {column!r}")
