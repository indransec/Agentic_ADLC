"""Personal access tokens and request authentication (T013, written before ado_sim.auth)."""

import base64
import hashlib
import hmac
import inspect
from pathlib import Path

import pytest

from ado_sim import auth
from ado_sim.auth import (
    TokenError,
    authenticate,
    hash_token,
    issue,
    list_tokens,
    revoke,
    token_from_header,
)
from ado_sim.db import Database, migrate
from ado_sim.seed import load_seed

KEY = "test-key-" + "x" * 32
SEED = Path(__file__).resolve().parents[2] / "seed" / "demo.yaml"
USER = "product.owner@adlc.demo"


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "a.db", create=True)
    migrate(database)
    load_seed(database, SEED)
    return database


def basic(token: str, user: str = "") -> str:
    return "Basic " + base64.b64encode(f"{user}:{token}".encode()).decode()


def test_token_shape_and_stored_hash(db: Database) -> None:
    token_id, token = issue(db, KEY, USER, label="laptop")
    assert len(token) == 52 and token.isalnum() and token == token.lower()
    with db.read() as conn:
        row = conn.execute("SELECT * FROM access_token WHERE id = ?", (token_id,)).fetchone()
    expected = hmac.new(KEY.encode(), token.encode(), hashlib.sha256).hexdigest()
    assert row["token_hash"] == expected == hash_token(KEY, token)
    assert token not in dict(row).values()
    db.close()


def test_tokens_are_random(db: Database) -> None:
    tokens = {issue(db, KEY, USER)[1] for _ in range(20)}
    assert len(tokens) == 20
    db.close()


def test_basic_and_bearer_authenticate(db: Database) -> None:
    _, token = issue(db, KEY, USER)
    for header in (basic(token), basic(token, "anyone"), f"Bearer {token}", f"bearer {token}"):
        identity = authenticate(db, KEY, header)
        assert identity is not None and identity.unique_name == USER
    db.close()


def test_every_bad_credential_is_refused_alike(db: Database) -> None:
    token_id, token = issue(db, KEY, USER)
    _, other = issue(db, KEY, USER)
    revoke(db, token_id)
    bad = [
        None,
        "",
        "Basic",
        "Basic !!!notbase64",
        "Basic " + base64.b64encode(b"no-colon").decode(),
        basic("x" * 52),
        basic(token),  # revoked
        "Digest " + other,
        "Bearer ",
    ]
    for header in bad:
        assert authenticate(db, KEY, header) is None
    assert authenticate(db, "another-key-" + "y" * 32, basic(other)) is None
    db.close()


def test_unknown_identity_and_revoke_and_list(db: Database) -> None:
    with pytest.raises(TokenError):
        issue(db, KEY, "nobody@adlc.demo")
    token_id, token = issue(db, KEY, USER, label="ci")
    listed = list_tokens(db, USER)
    assert [(t.id, t.unique_name, t.label, t.revoked_at) for t in listed] == [
        (token_id, USER, "ci", None)
    ]
    assert token not in repr(listed)
    assert revoke(db, token_id) is True
    assert revoke(db, token_id) is False
    assert revoke(db, 9999) is False
    assert list_tokens(db, USER)[0].revoked_at is not None
    assert len(list_tokens(db)) == 1
    db.close()


def test_header_parsing() -> None:
    assert token_from_header(basic("abc")) == "abc"
    assert token_from_header("Bearer abc") == "abc"
    assert token_from_header("Basic " + base64.b64encode(b"u:a:b").decode()) == "a:b"
    assert token_from_header("Token abc") is None


def test_comparison_is_constant_time() -> None:
    assert "compare_digest" in inspect.getsource(auth)
