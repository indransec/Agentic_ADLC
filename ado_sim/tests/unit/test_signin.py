"""017 T008: the three page credentials (FR-002; research R-03)."""

from __future__ import annotations

import pytest

from ado_sim import auth
from ado_sim.db import Database
from ado_sim.pages.signin import (
    REFUSED,
    SignInRefused,
    check_password,
    clear_password,
    hash_password,
    set_password,
    sign_in,
)
from tests.conftest import KEY, OWNER, SERVICE

PASSWORD = "owner-page-password"
DEMO = "shared-demo-password"


def test_hash_and_check() -> None:
    stored = hash_password(PASSWORD)
    assert stored.startswith("scrypt$") and PASSWORD not in stored
    assert check_password(PASSWORD, stored)
    assert not check_password("wrong-password!", stored)
    assert hash_password(PASSWORD) != stored  # salted


def test_a_page_password(db: Database) -> None:
    set_password(db, OWNER, PASSWORD)
    assert sign_in(db, KEY, OWNER, PASSWORD, demo_password=None).unique_name == OWNER


def test_the_shared_demo_password_only_when_set(db: Database) -> None:
    assert sign_in(db, KEY, OWNER, DEMO, demo_password=DEMO).unique_name == OWNER
    with pytest.raises(SignInRefused):
        sign_in(db, KEY, OWNER, DEMO, demo_password=None)


def test_a_personal_access_token_of_that_user_only(db: Database) -> None:
    _, token = auth.issue(db, KEY, OWNER)
    assert sign_in(db, KEY, OWNER, token, demo_password=None).unique_name == OWNER
    with pytest.raises(SignInRefused):
        sign_in(db, KEY, "engineering.lead@adlc.demo", token, demo_password=None)


def test_the_service_account_never_signs_in(db: Database) -> None:
    _, token = auth.issue(db, KEY, SERVICE)
    for credential in (token, DEMO):
        with pytest.raises(SignInRefused) as raised:
            sign_in(db, KEY, SERVICE, credential, demo_password=DEMO)
        assert str(raised.value) == REFUSED
    with pytest.raises(ValueError, match="service"):
        set_password(db, SERVICE, PASSWORD)


@pytest.mark.parametrize(
    ("user", "credential"),
    [(OWNER, "wrong-password!"), ("nobody@adlc.demo", PASSWORD), (OWNER, ""), ("", PASSWORD)],
)
def test_every_failure_has_the_same_message(db: Database, user: str, credential: str) -> None:
    set_password(db, OWNER, PASSWORD)
    with pytest.raises(SignInRefused) as raised:
        sign_in(db, KEY, user, credential, demo_password=None)
    assert str(raised.value) == REFUSED


def test_a_cleared_password_no_longer_works(db: Database) -> None:
    set_password(db, OWNER, PASSWORD)
    assert clear_password(db, OWNER)
    with pytest.raises(SignInRefused):
        sign_in(db, KEY, OWNER, PASSWORD, demo_password=None)
    assert not clear_password(db, OWNER)


def test_a_short_password_is_refused(db: Database) -> None:
    with pytest.raises(ValueError, match="12"):
        set_password(db, OWNER, "short")
