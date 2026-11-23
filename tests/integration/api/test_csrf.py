"""022 T030 (contracts/session.md, FR-014, N-02): a changing request that relies on the
browser's cookie must carry the session's CSRF value; bearer requests need none.

Written before the implementation (constitution IX for security rules).
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.integration.api.session_support import (
    COOKIE,
    CSRF,
    OWNER,
    bearer_sign_in,
    client_for,
    cookie_sign_in,
)
from tests.support.api import PASSWORD
from tests.support.orchestration import Harness

REFUSED = {"kind": "not_allowed", "detail": "cross-site request refused"}
SUBMISSION = {"name": "Claims triage", "intake_text": "x" * 250}


@pytest.fixture
def client(h: Harness, tmp_path: Path) -> Iterator[TestClient]:
    with client_for(h, tmp_path) as built:
        yield built


def count_usecases(client: TestClient, token: str) -> int:
    answer = client.get("/usecases?mine=false", headers={"Authorization": f"Bearer {token}"})
    return len(answer.json())


def test_a_cookie_change_without_the_header_is_refused(client: TestClient) -> None:
    cookie_sign_in(client)
    token = bearer_sign_in(client, "adlc_coe-person")
    answer = client.post("/usecases", json=SUBMISSION)
    assert answer.status_code == 403 and answer.json() == REFUSED
    assert count_usecases(client, token) == 0  # nothing was created


def test_a_wrong_value_is_refused(client: TestClient) -> None:
    cookie_sign_in(client)
    answer = client.post("/usecases", json=SUBMISSION, headers={CSRF: "guess"})
    assert answer.status_code == 403 and answer.json() == REFUSED


def test_another_sessions_value_is_refused(client: TestClient) -> None:
    other = cookie_sign_in(client, "product_owner-person")
    client.cookies.clear()
    cookie_sign_in(client)  # now the client holds the business owner's cookie
    answer = client.post("/usecases", json=SUBMISSION, headers={CSRF: str(other["csrf_token"])})
    assert answer.status_code == 403 and answer.json() == REFUSED


def test_the_right_value_is_accepted(client: TestClient) -> None:
    signed = cookie_sign_in(client)
    answer = client.post("/usecases", json=SUBMISSION, headers={CSRF: str(signed["csrf_token"])})
    assert answer.status_code == 201, answer.text


def test_reads_need_no_header(client: TestClient) -> None:
    cookie_sign_in(client)
    assert client.get("/usecases").status_code == 200


def test_bearer_changes_need_no_header(client: TestClient) -> None:
    token = bearer_sign_in(client)
    answer = client.post("/usecases", json=SUBMISSION, headers={"Authorization": f"Bearer {token}"})
    assert answer.status_code == 201, answer.text


def test_bearer_wins_over_a_cookie(client: TestClient) -> None:
    cookie_sign_in(client)
    token = bearer_sign_in(client)
    answer = client.post("/usecases", json=SUBMISSION, headers={"Authorization": f"Bearer {token}"})
    assert answer.status_code == 201, answer.text


def test_cookie_sign_in_needs_the_sign_in_header(client: TestClient) -> None:
    body = {"account_name": OWNER, "password": PASSWORD, "session": "cookie"}
    for headers in ({}, {CSRF: "something-else"}):
        answer = client.post("/auth/sign-in", json=body, headers=headers)
        assert answer.status_code == 403 and answer.json() == REFUSED
        assert "set-cookie" not in answer.headers
    assert COOKIE not in client.cookies


def test_sign_out_with_the_cookie_needs_the_header(client: TestClient) -> None:
    signed = cookie_sign_in(client)
    refused = client.post("/auth/sign-out")
    assert refused.status_code == 403 and refused.json() == REFUSED
    assert client.get("/auth/me").status_code == 200  # still signed in
    done = client.post("/auth/sign-out", headers={CSRF: str(signed["csrf_token"])})
    assert done.status_code == 204
