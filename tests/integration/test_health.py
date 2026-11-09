"""US1: per-service health check for the platform API (FR-003)."""

from pathlib import Path

from fastapi.testclient import TestClient

from adlc.api.app import create_app
from adlc.config.settings import Settings
from tests.integration.conftest import settings_for
from tests.support.pg import PlatformDatabase


def test_health_ok_without_auth(api_settings: Settings) -> None:
    with TestClient(create_app(api_settings)) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok"}}


def test_health_503_when_database_unreachable(
    platform_db: PlatformDatabase, tmp_path: Path
) -> None:
    accounts = tmp_path / "accounts.yaml"
    accounts.write_text("accounts: []\n")
    settings = settings_for(platform_db, accounts, db_port=1)
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "checks": {"database": "unavailable"}}


def test_health_body_reveals_no_connection_details(api_settings: Settings) -> None:
    with TestClient(create_app(api_settings)) as client:
        body = client.get("/health").text
    for value in (
        api_settings.db_host,
        str(api_settings.db_port),
        api_settings.db_app_user,
        api_settings.db_app_password.get_secret_value(),
    ):
        assert value not in body
