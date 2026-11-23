"""022 T029/T030: an API with every role's account, for the cookie-session and CSRF tests."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from tests.support.api import PASSWORD, api_for
from tests.support.orchestration import Harness

COOKIE = "adlc_session"
CSRF = "X-ADLC-CSRF"
OWNER = "business_owner-person"


@contextmanager
def client_for(h: Harness, tmp_path: Path) -> Iterator[TestClient]:
    """The API over the harness (registered specs), one account per role; no cookie yet."""
    with api_for(h, tmp_path) as built:
        yield built.client


def bearer_sign_in(client: TestClient, account: str = OWNER) -> str:
    answer = client.post("/auth/sign-in", json={"account_name": account, "password": PASSWORD})
    assert answer.status_code == 200, answer.text
    return str(answer.json()["token"])


def cookie_sign_in(client: TestClient, account: str = OWNER, **headers: str) -> dict[str, object]:
    """Cookie-mode sign-in; the client keeps the cookie. Returns the answer body."""
    answer = client.post(
        "/auth/sign-in",
        json={"account_name": account, "password": PASSWORD, "session": "cookie"},
        headers={CSRF: "sign-in", **headers},
    )
    assert answer.status_code == 200, answer.text
    return dict(answer.json())
