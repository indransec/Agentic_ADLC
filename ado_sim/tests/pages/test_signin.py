"""017 US1: signing in as a demo user (T015; FR-001..FR-004a)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from ado_sim import auth
from ado_sim.db import Database
from ado_sim.pages import sessions
from tests.conftest import KEY, LEAD, OWNER, SERVICE
from tests.pages import a11y
from tests.pages.conftest import BOARD, DEMO_PASSWORD, PASSWORD, csrf_of, sign_in


def test_no_session_shows_sign_in(client: TestClient) -> None:
    answer = client.get(BOARD)
    assert answer.status_code == 303 and answer.headers["location"].startswith("/_signin?next=")
    form = client.get("/_signin")
    assert form.status_code == 200
    assert OWNER in form.text and SERVICE not in form.text  # the service account is not offered
    assert a11y.problems(form.text) == []


def test_each_credential(client: TestClient, db: Database) -> None:
    _, token = auth.issue(db, KEY, LEAD)
    for user, credential in ((OWNER, PASSWORD), (OWNER, DEMO_PASSWORD), (LEAD, token)):
        sign_in(client, user, credential)
        page = client.get(BOARD)
        assert page.status_code == 200
        client.cookies.clear()


def test_one_message_for_every_refusal(client: TestClient) -> None:
    messages = set()
    for user, credential in (
        (OWNER, "wrong-password-1"),
        ("nobody@adlc.demo", PASSWORD),
        (SERVICE, DEMO_PASSWORD),
    ):
        form = client.get("/_signin")
        answer = client.post(
            "/_signin",
            data={
                "unique_name": user,
                "credential": credential,
                "next": "/",
                "csrf": csrf_of(form.text),
            },
        )
        assert answer.status_code == 400
        messages.add(answer.text.split('role="alert">')[1].split("<")[0])
    assert len(messages) == 1


def test_the_form_needs_its_csrf_token(client: TestClient) -> None:
    client.get("/_signin")
    answer = client.post(
        "/_signin", data={"unique_name": OWNER, "credential": PASSWORD, "csrf": "x"}
    )
    assert answer.status_code == 403


def test_sign_out_ends_the_session(client: TestClient) -> None:
    sign_in(client)
    page = client.get(BOARD)
    answer = client.post("/_signout", data={"csrf": csrf_of(page.text)})
    assert answer.status_code == 303
    assert client.get(BOARD).status_code == 303


def test_sign_out_needs_csrf(client: TestClient) -> None:
    sign_in(client)
    assert client.post("/_signout", data={"csrf": "x"}).status_code == 403


def test_an_expired_session(client: TestClient, db: Database) -> None:
    sign_in(client)
    with db.write() as conn:
        conn.execute(
            "UPDATE page_session SET expires_at = ?",
            ((datetime.now(UTC) - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),),
        )
    assert client.get(BOARD).status_code == 303


def test_next_is_only_a_local_path(client: TestClient) -> None:
    for target, expected in (("/x/y", "/x/y"), ("https://evil.test/", "/"), ("//evil.test", "/")):
        client.cookies.clear()
        form = client.get("/_signin")
        answer = client.post(
            "/_signin",
            data={
                "unique_name": OWNER,
                "credential": PASSWORD,
                "next": target,
                "csrf": csrf_of(form.text),
            },
        )
        assert answer.headers["location"] == expected


def test_a_cleared_password_ends_open_sessions(client: TestClient, db: Database) -> None:
    from ado_sim.pages.signin import clear_password

    sign_in(client)
    clear_password(db, OWNER)
    assert client.get(BOARD).status_code == 303
    assert sessions.housekeeping(db) >= 1
