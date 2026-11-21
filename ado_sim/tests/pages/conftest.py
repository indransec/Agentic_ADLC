"""Page test fixtures (017 T014): a seeded simulator, page passwords, signed-in clients."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from ado_sim.app import create_app
from ado_sim.db import Database
from ado_sim.pages.signin import set_password
from ado_sim.settings import Settings
from tests.conftest import LEAD, OWNER

PASSWORD = "page-password-123"
BOARD = "/adlc-demo/Agentic%20ADLC/_boards/board"
ITEM = "/adlc-demo/Agentic%20ADLC/_workitems/edit/"
DEMO_PASSWORD = "shared-demo-pass-1"
_CSRF = re.compile(r'name="csrf" value="([^"]+)"')


def csrf_of(html: str) -> str:
    match = _CSRF.search(html)
    assert match is not None, "no CSRF field on the page"
    return match.group(1)


@pytest.fixture
def client(settings: Settings, db: Database) -> Iterator[TestClient]:
    for user in (OWNER, LEAD):
        set_password(db, user, PASSWORD)
    app = create_app(replace(settings, demo_password=DEMO_PASSWORD))
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client


def sign_in(client: TestClient, user: str = OWNER, credential: str = PASSWORD) -> TestClient:
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
    assert answer.status_code == 303, answer.text
    return client


@pytest.fixture
def signed_in(client: TestClient) -> Callable[..., TestClient]:
    def make(user: str = OWNER, credential: str = PASSWORD) -> TestClient:
        return sign_in(client, user, credential)

    return make
