"""US3 (T062): no secret value reaches logs or output during a full cycle (SC-008, FR-015)."""

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from adlc.api.app import create_app
from adlc.identity.hashing import hash_password
from tests.integration.conftest import settings_for
from tests.support.db import PlatformDatabase

PASSWORD = "cycle-password-distinctive-123"
SESSION_SECRET = "cycle-session-secret-distinctive-" + "k" * 8


def test_full_cycle_logs_no_secrets(
    migrated_db: PlatformDatabase,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    credential_hash = hash_password(PASSWORD)
    accounts = tmp_path / "accounts.yaml"
    accounts.write_text(
        "accounts:\n  - {account_name: owner.business, display_name: O, "
        f"roles: [business_owner], credential_hash: '{credential_hash}'}}\n"
    )
    settings = settings_for(migrated_db, accounts, session_secret=SESSION_SECRET, log_level="DEBUG")
    caplog.set_level(logging.DEBUG)

    with TestClient(create_app(settings)) as client:
        client.post("/auth/sign-in", json={"account_name": "owner.business", "password": "bad"})
        token = client.post(
            "/auth/sign-in", json={"account_name": "owner.business", "password": PASSWORD}
        ).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/auth/me", headers=headers).status_code == 200
        assert client.get("/health").status_code == 200
        assert client.post("/auth/sign-out", headers=headers).status_code == 204

    captured = capsys.readouterr()
    everything = "\n".join(
        [caplog.text, captured.out, captured.err]
        + [repr(vars(record)) for record in caplog.records]
    )
    secrets = {
        "session secret": SESSION_SECRET,
        "user password": PASSWORD,
        "credential hash": credential_hash,
        "session token": token,
    }
    leaked = [name for name, value in secrets.items() if value in everything]
    assert leaked == []
