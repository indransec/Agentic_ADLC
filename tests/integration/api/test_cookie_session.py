"""022 T029 (contracts/session.md, FR-013, FR-015, FR-016, FR-019): the browser's session is an
HttpOnly cookie that page scripts cannot read; bearer clients are unchanged.

Written before the implementation (constitution IX for security rules).
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from adlc.api.auth import PUBLIC_PATHS
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


@pytest.fixture
def client(h: Harness, tmp_path: Path) -> Iterator[TestClient]:
    with client_for(h, tmp_path) as built:
        yield built


def set_cookie(answer: object) -> str:
    headers = answer.headers  # type: ignore[attr-defined]
    cookies = [v for k, v in headers.multi_items() if k.lower() == "set-cookie"]
    assert len(cookies) == 1, cookies
    return str(cookies[0])


def test_bearer_sign_in_is_unchanged(client: TestClient) -> None:
    answer = client.post("/auth/sign-in", json={"account_name": OWNER, "password": PASSWORD})
    assert answer.status_code == 200
    assert set(answer.json()) == {"token", "token_type", "expires_at", "person"}
    assert answer.json()["token_type"] == "bearer"
    assert "set-cookie" not in answer.headers


def test_cookie_sign_in_sets_an_httponly_strict_cookie(client: TestClient) -> None:
    answer = client.post(
        "/auth/sign-in",
        json={"account_name": OWNER, "password": PASSWORD, "session": "cookie"},
        headers={CSRF: "sign-in"},
    )
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert set(body) == {"expires_at", "person", "csrf_token"}
    assert body["person"]["account_name"] == OWNER
    cookie = set_cookie(answer)
    attributes = [part.strip() for part in cookie.split(";")]
    name, _, token = attributes[0].partition("=")
    assert name == COOKIE and token
    lowered = {a.lower() for a in attributes[1:]}
    assert {"httponly", "samesite=strict", "path=/"} <= lowered
    assert any(a.startswith("max-age=") and int(a.split("=")[1]) > 0 for a in lowered)
    assert "secure" not in lowered  # plain http here
    assert token not in answer.text  # the token is never in the body (FR-013)


def test_secure_when_the_original_scheme_is_https(client: TestClient) -> None:
    answer = client.post(
        "/auth/sign-in",
        json={"account_name": OWNER, "password": PASSWORD, "session": "cookie"},
        headers={CSRF: "sign-in", "X-Forwarded-Proto": "https"},
    )
    assert answer.status_code == 200
    assert "secure" in {a.strip().lower() for a in set_cookie(answer).split(";")}


def test_reads_with_the_cookie(client: TestClient) -> None:
    signed = cookie_sign_in(client)
    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["account_name"] == OWNER
    assert me.json()["csrf_token"] == signed["csrf_token"]
    assert client.get("/usecases").status_code == 200


def test_bearer_me_has_no_csrf_token(client: TestClient) -> None:
    token = bearer_sign_in(client)
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and "csrf_token" not in me.json()


def test_no_cookie_and_no_bearer_is_not_signed_in(client: TestClient) -> None:
    answer = client.get("/auth/me")
    assert answer.status_code == 401 and answer.json()["kind"] == "not_signed_in"


def test_a_forged_cookie_is_not_signed_in(client: TestClient) -> None:
    client.cookies.set(COOKIE, "not-a-real-token")
    assert client.get("/auth/me").status_code == 401


def test_sign_out_clears_the_cookie_and_revokes_the_session(client: TestClient) -> None:
    signed = cookie_sign_in(client)
    token = client.cookies.get(COOKIE)
    assert token
    out = client.post("/auth/sign-out", headers={CSRF: str(signed["csrf_token"])})
    assert out.status_code == 204
    cleared = [a.strip().lower() for a in set_cookie(out).split(";")]
    assert cleared[0] == f"{COOKIE}=" or cleared[0] == f'{COOKIE}=""'
    assert "max-age=0" in cleared
    client.cookies.clear()
    client.cookies.set(COOKIE, token)  # the old cookie, replayed
    assert client.get("/auth/me").status_code == 401


def test_wrong_password_in_cookie_mode(client: TestClient) -> None:
    answer = client.post(
        "/auth/sign-in",
        json={"account_name": OWNER, "password": "wrong-password", "session": "cookie"},
        headers={CSRF: "sign-in"},
    )
    assert answer.status_code == 401
    assert answer.json() == {"kind": "not_signed_in", "detail": "invalid credentials"}
    assert "set-cookie" not in answer.headers


def test_public_paths_are_unchanged() -> None:
    assert frozenset({"/health", "/auth/sign-in"}) == PUBLIC_PATHS
