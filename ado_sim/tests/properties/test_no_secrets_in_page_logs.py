"""017 SC-004, FR-015: no password, token, session id, CSRF token or form value in any log line
(T032)."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from ado_sim import auth
from ado_sim.db import Database
from ado_sim.pages import sessions
from tests.conftest import KEY, LEAD, OWNER
from tests.pages.conftest import BOARD, DEMO_PASSWORD, PASSWORD, csrf_of, sign_in

MARKERS = ("MARK-TITLE-91", "MARK-DESC-42", "MARK-WRONG-PASSWORD-7")


def test_page_logs_hold_no_secrets(
    client: TestClient,
    db: Database,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    _, token = auth.issue(db, KEY, LEAD)
    secrets_seen: list[str] = [PASSWORD, DEMO_PASSWORD, token]
    for user, credential in ((OWNER, PASSWORD), (OWNER, DEMO_PASSWORD), (LEAD, token)):
        sign_in(client, user, credential)
        secrets_seen.append(client.cookies.get(sessions.COOKIE) or "")
        page = client.get(BOARD)
        secrets_seen.append(csrf_of(page.text))
        client.post(
            BOARD + "/epics",
            data={"csrf": csrf_of(page.text), "title": MARKERS[0], "description": MARKERS[1]},
        )
        client.post(
            BOARD + "/epics",
            data={"csrf": csrf_of(page.text), "title": "", "description": MARKERS[1]},
        )
        client.post("/_signout", data={"csrf": csrf_of(page.text)})
        client.cookies.clear()
    form = client.get("/_signin")
    client.post(
        "/_signin",
        data={"unique_name": OWNER, "credential": MARKERS[2], "csrf": csrf_of(form.text)},
    )
    logged = caplog.text
    assert "request method=" in logged
    for secret in [*secrets_seen, *MARKERS]:
        assert secret and secret not in logged, secret[:12]
