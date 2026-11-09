"""US3: settings fail fast with named, value-free errors (FR-013 to FR-015, SC-005)."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from adlc.config.errors import format_settings_error
from adlc.config.settings import Settings

APP_PW = "app-password-value-0001"
SESSION = "session-secret-value-0000000000000001"
REQUIRED = (
    "ADLC_ENV",
    "ADLC_DB_HOST",
    "ADLC_DB_APP_PASSWORD",
    "ADLC_SESSION_SECRET",
    "ADLC_ACCOUNTS_FILE",
)


@pytest.fixture
def valid_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, str]:
    accounts = tmp_path / "accounts.yaml"
    accounts.write_text("accounts: []\n")
    for key in list(os.environ):
        if key.startswith("ADLC_"):
            monkeypatch.delenv(key)
    env = {
        "ADLC_ENV": "dev",
        "ADLC_DB_HOST": "localhost",
        "ADLC_DB_APP_PASSWORD": APP_PW,
        "ADLC_SESSION_SECRET": SESSION,
        "ADLC_ACCOUNTS_FILE": str(accounts),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return env


def _error() -> str:
    try:
        Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        return format_settings_error(exc, Settings)
    raise AssertionError("expected a validation error")


def test_valid_settings_load(valid_env: dict[str, str]) -> None:
    settings = Settings()  # type: ignore[call-arg]
    assert settings.env == "dev"
    assert settings.session_ttl.total_seconds() == 8 * 3600
    assert settings.db_port == 5432


@pytest.mark.parametrize("name", REQUIRED)
def test_missing_required_setting_is_named(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.delenv(name)
    output = _error()
    assert output.startswith("adlc: configuration error\n")
    assert f"  {name}: missing; expected " in output


@pytest.mark.parametrize("name", REQUIRED)
def test_empty_value_counts_as_missing(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(name, "")
    assert f"  {name}: missing;" in _error()


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("ADLC_DB_PORT", "abc", "ADLC_DB_PORT: invalid; expected integer 1-65535"),
        ("ADLC_DB_PORT", "70000", "ADLC_DB_PORT: invalid; expected integer 1-65535"),
        ("ADLC_ENV", "prod", "ADLC_ENV: invalid; expected dev or demo"),
        (
            "ADLC_SESSION_SECRET",
            "short",
            "ADLC_SESSION_SECRET: invalid; expected at least 32 characters (secret)",
        ),
        ("ADLC_SESSION_TTL", "5m", "ADLC_SESSION_TTL: invalid; expected <int><unit>"),
        (
            "ADLC_ACCOUNTS_FILE",
            "/does/not/exist.yaml",
            "ADLC_ACCOUNTS_FILE: invalid; expected path to a readable file",
        ),
    ],
)
def test_invalid_setting_names_expected_form(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, name: str, value: str, expected: str
) -> None:
    monkeypatch.setenv(name, value)
    assert expected in _error()


def test_error_output_never_contains_values(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADLC_SESSION_SECRET", "tiny-secret-value")
    monkeypatch.setenv("ADLC_DB_PORT", "port-value-xyz")
    monkeypatch.setenv("ADLC_ENV", "env-value-xyz")
    output = _error()
    for value in ("tiny-secret-value", "port-value-xyz", "env-value-xyz", APP_PW):
        assert value not in output


def test_repr_and_dump_hide_secrets(valid_env: dict[str, str]) -> None:
    settings = Settings()  # type: ignore[call-arg]
    for text in (repr(settings), str(settings), settings.model_dump_json()):
        assert APP_PW not in text
        assert SESSION not in text
