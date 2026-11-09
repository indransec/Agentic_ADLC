"""US4: sign-in, current person, sign-out, deny by default (FR-017 to FR-021a)."""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adlc.api.app import create_app
from adlc.identity.hashing import hash_password
from tests.integration.conftest import settings_for
from tests.support.pg import PlatformDatabase

PASSWORD = "correct-password-for-tests"


@pytest.fixture
def app(platform_db: PlatformDatabase, tmp_path: Path) -> FastAPI:
    accounts = tmp_path / "accounts.yaml"
    accounts.write_text(
        "accounts:\n"
        "  - account_name: owner.business\n"
        "    display_name: Demo Business Owner\n"
        "    roles: [business_owner, product_owner]\n"
        f"    credential_hash: '{hash_password(PASSWORD)}'\n"
        "  - account_name: placeholder.user\n"
        "    display_name: Not Set Up\n"
        "    roles: [adlc_coe]\n"
        "    credential_hash: REPLACE_WITH_HASH\n"
    )
    application = create_app(settings_for(platform_db, accounts))

    @application.get("/test-only/protected")
    def protected() -> dict[str, str]:
        return {"ok": "yes"}

    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _sign_in(client: TestClient, name: str, password: str) -> tuple[int, dict[str, object]]:
    response = client.post("/auth/sign-in", json={"account_name": name, "password": password})
    return response.status_code, response.json()


def test_sign_in_and_me(client: TestClient) -> None:
    status, body = _sign_in(client, "owner.business", PASSWORD)
    assert status == 200
    assert body["token_type"] == "bearer"
    assert {"token", "expires_at", "person"} <= set(body)
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200
    assert me.json() == {
        "account_name": "owner.business",
        "display_name": "Demo Business Owner",
        "roles": ["business_owner", "product_owner"],
    }


def test_refusals_are_identical(client: TestClient) -> None:
    unknown = client.post("/auth/sign-in", json={"account_name": "nobody", "password": "x"})
    wrong = client.post("/auth/sign-in", json={"account_name": "owner.business", "password": "x"})
    placeholder = client.post(
        "/auth/sign-in", json={"account_name": "placeholder.user", "password": "REPLACE_WITH_HASH"}
    )
    for response in (unknown, wrong, placeholder):
        assert response.status_code == 401
        assert response.content == unknown.content
    assert unknown.json() == {"detail": "invalid credentials"}


@pytest.mark.parametrize("header", [None, "Bearer garbage", "Basic abc", "Bearer "])
def test_me_requires_valid_session(client: TestClient, header: str | None) -> None:
    headers = {"Authorization": header} if header is not None else {}
    response = client.get("/auth/me", headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "not authenticated"}


def test_sign_out_revokes(client: TestClient) -> None:
    _, body = _sign_in(client, "owner.business", PASSWORD)
    headers = {"Authorization": f"Bearer {body['token']}"}
    assert client.post("/auth/sign-out", headers=headers).status_code == 204
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_deny_by_default_for_new_routes(client: TestClient) -> None:
    assert client.get("/test-only/protected").status_code == 401
    _, body = _sign_in(client, "owner.business", PASSWORD)
    response = client.get(
        "/test-only/protected", headers={"Authorization": f"Bearer {body['token']}"}
    )
    assert response.status_code == 200


def test_docs_require_sign_in(client: TestClient) -> None:
    assert client.get("/docs").status_code == 401
    assert client.get("/openapi.json").status_code == 401


def test_health_and_sign_in_are_public(client: TestClient) -> None:
    assert client.get("/health").status_code == 200
    assert client.post("/auth/sign-in", json={}).status_code == 422


def test_sign_in_logging_has_no_secrets(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    _sign_in(client, "owner.business", "wrong-password-xyz")
    _, body = _sign_in(client, "owner.business", PASSWORD)
    token = str(body["token"])
    client.post("/auth/sign-out", headers={"Authorization": f"Bearer {token}"})
    messages = [record.getMessage() for record in caplog.records]
    assert any("auth.sign_in" in m and "outcome=refused" in m for m in messages)
    assert any("auth.sign_in" in m and "outcome=success" in m for m in messages)
    assert any("auth.sign_out" in m for m in messages)
    joined = "\n".join(messages) + caplog.text
    for secret in (PASSWORD, "wrong-password-xyz", token, "scrypt$"):
        assert secret not in joined


def test_many_failures_do_not_lock(client: TestClient) -> None:
    for _ in range(10):
        _sign_in(client, "owner.business", "wrong")
    status, _ = _sign_in(client, "owner.business", PASSWORD)
    assert status == 200


def test_bad_account_file_stops_app(platform_db: PlatformDatabase, tmp_path: Path) -> None:
    accounts = tmp_path / "accounts.yaml"
    accounts.write_text(
        "accounts:\n  - {account_name: a.b, display_name: A, roles: [no_such_role], "
        "credential_hash: REPLACE_WITH_HASH}\n"
    )
    with pytest.raises(Exception, match=r"a\.b.*no_such_role"):
        create_app(settings_for(platform_db, accounts))
